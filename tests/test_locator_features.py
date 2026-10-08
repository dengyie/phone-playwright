"""增强单元测试: PhoneLocator 链式选择器、first/last/nth 作用域过滤与 Trace 失败帧捕获。"""

import json
import os
import tempfile
import zipfile
import pytest
from phone_playwright.models.geometry import Rect
from phone_playwright.models.schema import RawNode, CompactElement
from phone_playwright.models.exceptions import ActionabilityTimeoutError
from phone_playwright.drivers.base import BaseDriver
from phone_playwright.core.pruner import SemanticPruner
from phone_playwright.core.locator import PhoneLocator
from phone_playwright.api.async_api import AsyncPhonePage, AsyncPhoneDevice


class FakeChainedDriver(BaseDriver):
    def __init__(self) -> None:
        super().__init__("fake-chained-dev")
        self.taps: list[tuple[int, int]] = []

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def get_viewport_size(self) -> tuple[int, int]:
        return (1080, 2400)

    async def dump_raw_tree(self) -> RawNode:
        btn1 = RawNode(
            class_name="android.widget.Button",
            text="添加到购物车",
            bounds=Rect(left=100, top=100, right=300, bottom=200),
            clickable=True,
            enabled=True,
        )
        btn2 = RawNode(
            class_name="android.widget.Button",
            text="添加到购物车",
            bounds=Rect(left=100, top=300, right=300, bottom=400),
            clickable=True,
            enabled=True,
        )
        btn3 = RawNode(
            class_name="android.widget.Button",
            text="立即结算",
            bounds=Rect(left=100, top=500, right=300, bottom=600),
            clickable=True,
            enabled=True,
        )
        return RawNode(
            class_name="android.widget.FrameLayout",
            bounds=Rect(left=0, top=0, right=1080, bottom=2400),
            children=[btn1, btn2, btn3],
        )

    async def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))

    async def type_text(self, text: str) -> None:
        pass

    async def swipe(self, sx: int, sy: int, ex: int, ey: int, duration_ms: int = 300) -> None:
        pass

    async def long_press(self, x: int, y: int, duration_ms: int = 800) -> None:
        pass

    async def press_key(self, key: str | int) -> None:
        pass

    async def take_screenshot(self) -> bytes:
        return b""

    async def get_current_app(self) -> tuple[str | None, str | None]:
        return ("com.shop.app", "MainActivity")


@pytest.mark.asyncio
async def test_chained_locator_first_last_and_nth() -> None:
    driver = FakeChainedDriver()
    pruner = SemanticPruner()
    page = AsyncPhonePage(driver=driver, pruner=pruner)

    # 1. 验证链式定位子项与 nth(0)
    first_cart = page.locator("role=button").first()
    res = await first_cart.click()
    assert res.success is True
    # 命中首个按钮 ( (100+300)//2, (100+200)//2 ) = (200, 150)
    assert driver.taps[-1] == (200, 150)

    # 2. 验证 nth(1)
    second_cart = page.locator("role=button").nth(1)
    res2 = await second_cart.click()
    assert res2.success is True
    # 命中第二个按钮 (200, 350)
    assert driver.taps[-1] == (200, 350)

    # 3. 验证 last()
    last_btn = page.locator("role=button").last()
    res3 = await last_btn.click()
    assert res3.success is True
    # 命中最后一个按钮 (200, 550)
    assert driver.taps[-1] == (200, 550)

    # 4. 验证链式子选择器: page.locator("role=button").locator("text=立即结算")
    checkout_btn = page.locator("role=button").locator("text=立即结算")
    res4 = await checkout_btn.click()
    assert res4.success is True
    assert driver.taps[-1] == (200, 550)


@pytest.mark.asyncio
async def test_tracing_captures_failure_events() -> None:
    driver = FakeChainedDriver()
    dev = AsyncPhoneDevice(driver=driver)

    await dev.tracing.start(screenshots=False, snapshots=True)
    page = dev.current_page

    # 尝试点击不存在的目标以触发未命中并录制 failure 事件
    from phone_playwright.models.exceptions import SelectorNotFoundError
    with pytest.raises(SelectorNotFoundError):
        await page.locator("text=绝对不存在的按钮").click(timeout_s=0.3)

    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = os.path.join(tmpdir, "failed-trace.zip")
        out = await dev.tracing.stop(path=trace_path)
        assert os.path.exists(out)

        with zipfile.ZipFile(out, "r") as zf:
            trace_lines = zf.read("trace.trace").decode("utf-8").strip().splitlines()
            assert len(trace_lines) >= 1
            last_event = json.loads(trace_lines[-1])
            assert last_event["type"] == "action"
            assert last_event["name"] == "click_failed"
            assert "error" in last_event
            assert "SelectorNotFoundError" in last_event["metadata"]["error_type"]
