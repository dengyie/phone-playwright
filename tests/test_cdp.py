"""v2 核心模块单元测试: WebView CDP 穿透与 DOM 坐标映射。"""

import json
import pytest
from phone_playwright.core.cdp import (
    CdpDiscovery,
    WebFrameLocator,
    WebPhoneLocator,
    _find_free_port,
)


class FakePageForCdp:
    def __init__(self, driver: object) -> None:
        self.driver = driver
        self.action_engine = FakeActionEngine()

    def locator(self, selector: str) -> object:
        return FakeContainerLocator()


class FakeActionEngine:
    def invalidate_cache(self) -> None:
        pass


class FakeContainerLocator:
    async def bounding_box(self) -> dict[str, int]:
        return {"x": 50, "y": 100, "width": 800, "height": 1200}


class FakeAdbDriverForCdp:
    def __init__(self) -> None:
        self.taps: list[tuple[int, int]] = []
        self.adb_calls: list[tuple[str, ...]] = []

    async def _run_adb(self, *args: str) -> str:
        self.adb_calls.append(args)
        if args == ("shell", "cat", "/proc/net/unix"):
            return """
Num RefCount Protocol Flags Type St Path
0000000000000000: 00000002 00000000 00010000 0001 01 12345 @webview_devtools_remote_10824
0000000000000000: 00000002 00000000 00010000 0001 01 67890 /dev/socket/adbd
"""
        return ""

    async def get_viewport_size(self) -> tuple[int, int]:
        return 1080, 2400

    async def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))


def test_find_free_port() -> None:
    port = _find_free_port()
    assert isinstance(port, int)
    assert 1024 < port < 65535


@pytest.mark.asyncio
async def test_cdp_discovery_remote_sockets() -> None:
    driver = FakeAdbDriverForCdp()
    sockets = await CdpDiscovery.discover_remote_sockets(driver)  # type: ignore[arg-type]
    assert len(sockets) == 1
    assert sockets[0] == "webview_devtools_remote_10824"


@pytest.mark.asyncio
async def test_web_phone_locator_coordinate_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    driver = FakeAdbDriverForCdp()
    page = FakePageForCdp(driver=driver)
    frame = WebFrameLocator(page=page)  # type: ignore[arg-type]

    # Mock _ensure_connected 返回一个假 CdpClient
    class FakeCdpClient:
        def __init__(self) -> None:
            self._closed = False
            self.eval_calls: list[str] = []

        async def get_element_box(self, selector: str) -> dict[str, object]:
            # DOM 相对 WebView 视口坐标: x=30, y=40, w=100, h=50
            return {"x": 30, "y": 40, "width": 100, "height": 50, "text": "立即购买"}

        async def evaluate(self, js: str) -> object:
            self.eval_calls.append(js)
            return "测试结果"

        async def get_title(self) -> str:
            return "H5 商品详情页"

        async def get_url(self) -> str:
            return "https://m.shop.com/item/123"

        async def close(self) -> None:
            self._closed = True

    fake_client = FakeCdpClient()

    async def fake_ensure_connected() -> FakeCdpClient:
        return fake_client

    monkeypatch.setattr(frame, "_ensure_connected", fake_ensure_connected)

    title = await frame.title()
    url = await frame.url()
    assert title == "H5 商品详情页"
    assert url == "https://m.shop.com/item/123"

    loc = frame.locator("button.buy-now")
    res = await loc.click(timeout_s=1.0)
    assert res.success is True
    assert res.verb == "click"

    # 容器起点 (50, 100)，DOM 中心 (30 + 50, 40 + 25) = (80, 65)
    # 绝对屏幕点击落点应该是 (50 + 80, 100 + 65) = (130, 165)
    assert len(driver.taps) == 1
    assert driver.taps[0] == (130, 165)

    # 验证 text_content
    text = await loc.text_content(timeout_s=1.0)
    assert text == "立即购买"

    # 验证 fill
    fill_res = await loc.fill("12345", timeout_s=1.0)
    assert fill_res.success is True
    assert len(fake_client.eval_calls) > 0

    await frame.close()


@pytest.mark.asyncio
async def test_create_cdp_client_cleanup_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    driver = FakeAdbDriverForCdp()

    # 模拟探测失败触发异常
    def fake_fetch_fail(*args: object, **kwargs: object) -> object:
        raise OSError("Connection refused")

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_fetch_fail)

    with pytest.raises(Exception):
        await CdpDiscovery.create_cdp_client(driver)  # type: ignore[arg-type]

    # 断言 forward 建立后在失败时执行了 forward --remove
    forward_adds = [c for c in driver.adb_calls if c and c[0] == "forward" and not c[1].startswith("--")]
    forward_removes = [c for c in driver.adb_calls if c and len(c) >= 3 and c[0] == "forward" and c[1] == "--remove"]
    assert len(forward_adds) == 1
    assert len(forward_removes) == 1
    assert forward_adds[0][1] == forward_removes[0][2]


@pytest.mark.asyncio
async def test_cdp_client_get_element_box_with_dpr(monkeypatch: pytest.MonkeyPatch) -> None:
    from phone_playwright.core.cdp import CdpClient

    client = CdpClient(ws_url="ws://127.0.0.1:9222/devtools/page/1", local_port=9222)
    # Mock evaluate 模拟包含 DPR=2.625 时的返回结果
    async def fake_eval(expr: str, timeout: float = 10.0) -> object:
        return {
            "x": 262.5,
            "y": 525.0,
            "width": 131.25,
            "height": 78.75,
            "css_x": 100.0,
            "css_y": 200.0,
            "css_width": 50.0,
            "css_height": 30.0,
            "dpr": 2.625,
            "text": "加入购物车",
        }

    monkeypatch.setattr(client, "evaluate", fake_eval)
    box = await client.get_element_box("#add-to-cart")
    assert box is not None
    assert box["dpr"] == 2.625
    assert box["x"] == 262.5
    assert box["text"] == "加入购物车"
