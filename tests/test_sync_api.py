import pytest
from phone_playwright.models.geometry import Rect
from phone_playwright.models.schema import RawNode
from phone_playwright.drivers.base import BaseDriver
from phone_playwright.core.pruner import SemanticPruner
from phone_playwright.api.sync_api import sync_phone_playwright
from phone_playwright.models.exceptions import ActionabilityTimeoutError, OffscreenElementError


class DummySyncDriver(BaseDriver):
    def __init__(self, device_id: str = "dummy-dev") -> None:
        super().__init__(device_id)
        self.clicked_coords: list[tuple[int, int]] = []
        self.typed_texts: list[str] = []
        self.pressed_keys: list[str | int] = []
        self.long_presses: list[tuple[int, int, int]] = []

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def get_viewport_size(self) -> tuple[int, int]:
        return (1080, 2400)

    async def dump_raw_tree(self) -> RawNode:
        btn1 = RawNode(
            class_name="android.widget.Button",
            text="登录",
            bounds=Rect(left=100, top=200, right=500, bottom=300),
            clickable=True,
            enabled=True,
        )
        return RawNode(
            class_name="android.widget.FrameLayout",
            bounds=Rect(left=0, top=0, right=1080, bottom=2400),
            children=[btn1],
        )

    async def tap(self, x: int, y: int) -> None:
        self.clicked_coords.append((x, y))

    async def type_text(self, text: str) -> None:
        self.typed_texts.append(text)

    async def swipe(self, sx: int, sy: int, ex: int, ey: int, duration_ms: int = 300) -> None:
        pass

    async def long_press(self, x: int, y: int, duration_ms: int = 800) -> None:
        self.long_presses.append((x, y, duration_ms))

    async def press_key(self, key: str | int) -> None:
        self.pressed_keys.append(key)

    async def take_screenshot(self) -> bytes:
        return b"fake-png"

    async def get_current_app(self) -> tuple[str | None, str | None]:
        return "com.test.login", "LoginActivity"


def test_sync_playwright_workflow(monkeypatch):
    driver_instance = DummySyncDriver("mock-1")

    with sync_phone_playwright() as p:
        # monkeypatch fleet.get_driver 直接返回我们的 mock driver
        async def fake_get_driver(alias_or_id: str):
            return driver_instance

        monkeypatch.setattr(p._async_playwright.fleet, "get_driver", fake_get_driver)

        device = p.connect("mock-1")
        # 兼容 device.current_page 和 device.current_page()
        page = device.current_page()

        # 1. 抓取快照并验证 Markdown 格式输出
        snapshot = page.snapshot()
        md = snapshot.to_markdown()
        assert "Active App: com.test.login" in md
        assert '[@1] button: "登录"' in md

        # 2. 模拟 Playwright 同步点击
        result = page.locator("@1").click()
        assert result.success
        assert driver_instance.clicked_coords == [(300, 250)]

        # 3. 模拟 hover (长按) 与 wait_for
        hover_res = page.locator("@1").hover(duration_ms=600)
        assert hover_res.success
        assert driver_instance.long_presses == [(300, 250, 600)]

        wait_res = page.locator("@1").wait_for(state="visible")
        assert wait_res.success

        # 4. 模拟按键与手势
        page.press_back()
        page.press_home()
        assert driver_instance.pressed_keys == ["back", "home"]

        # 5. 验证快捷定位器 get_by_test_id
        test_loc = device.get_by_test_id("com.test:id/btn")
        assert test_loc.selector == "id=com.test:id/btn"


def test_sync_playwright_locator_warm_cache_reuse(monkeypatch):
    class CountingDriver(DummySyncDriver):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.dump_count = 0

        async def dump_raw_tree(self):
            self.dump_count += 1
            return await super().dump_raw_tree()

    driver_instance = CountingDriver("mock-cache")

    with sync_phone_playwright() as p:
        async def fake_get_driver(alias_or_id: str):
            return driver_instance

        monkeypatch.setattr(p._async_playwright.fleet, "get_driver", fake_get_driver)
        device = p.connect("mock-cache")
        page = device.current_page

        loc = page.locator("text=登录")
        vis = loc.is_visible()
        box = loc.bounding_box()
        txt = loc.text_content()

        assert vis is True
        assert box == {"x": 100, "y": 200, "width": 400, "height": 100}
        assert txt == "登录"
        # 验证 1.0s 内连续读取复用温热缓存，dump_raw_tree 仅调用 1 次
        assert driver_instance.dump_count == 1

