"""v2 核心模块单元测试: Expect 断言库与 Trace Viewer 录制器。"""

import json
import os
import re
import tempfile
import zipfile
import pytest
from phone_playwright.models.geometry import Rect
from phone_playwright.models.schema import CompactElement, PageSnapshot, RawNode
from phone_playwright.core.assertions import expect, AsyncExpect
from phone_playwright.tracing.recorder import TraceRecorder


class FakeLocator:
    def __init__(
        self,
        selector: str = "text=确认",
        visible: bool = True,
        enabled: bool = True,
        text: str = "确认提交",
        count_val: int = 1,
    ) -> None:
        self.selector = selector
        self._visible = visible
        self._enabled = enabled
        self._text = text
        self._count = count_val

    async def is_visible(self) -> bool:
        return self._visible

    async def is_enabled(self) -> bool:
        return self._enabled

    async def is_disabled(self) -> bool:
        return not self._enabled

    async def text_content(self) -> str | None:
        return self._text

    async def count(self) -> int:
        return self._count


class FakeTraceDriver:
    def __init__(self, device_id: str = "test-device-1") -> None:
        self.device_id = device_id
        self.taps: list[tuple[int, int]] = []

    async def get_viewport_size(self) -> tuple[int, int]:
        return 1080, 2400

    async def dump_raw_tree(self) -> RawNode:
        return RawNode(
            bounds=Rect(left=100, top=200, right=300, bottom=400),
            text="确认提交",
            clickable=True,
            enabled=True,
        )

    async def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))


@pytest.mark.asyncio
async def test_expect_visible_and_hidden() -> None:
    loc_vis = FakeLocator(visible=True)
    await expect(loc_vis, timeout_s=0.5).to_be_visible()  # type: ignore[arg-type]

    loc_hid = FakeLocator(visible=False)
    await expect(loc_hid, timeout_s=0.5).to_be_hidden()  # type: ignore[arg-type]

    with pytest.raises(AssertionError):
        await expect(loc_hid, timeout_s=0.2).to_be_visible()  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_expect_text_and_regex() -> None:
    loc = FakeLocator(text="欢迎光临商城")
    await expect(loc, timeout_s=0.5).to_have_text("欢迎光临商城")  # type: ignore[arg-type]
    await expect(loc, timeout_s=0.5).to_contain_text("光临")  # type: ignore[arg-type]
    await expect(loc, timeout_s=0.5).to_have_text(re.compile(r"欢迎.*商城"))  # type: ignore[arg-type]

    with pytest.raises(AssertionError):
        await expect(loc, timeout_s=0.2).to_have_text("错误文本")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_expect_count_and_enabled() -> None:
    loc = FakeLocator(count_val=3, enabled=True)
    await expect(loc, timeout_s=0.5).to_have_count(3)  # type: ignore[arg-type]
    await expect(loc, timeout_s=0.5).to_be_enabled()  # type: ignore[arg-type]

    with pytest.raises(AssertionError):
        await expect(loc, timeout_s=0.2).to_be_disabled()  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_trace_recorder_lifecycle() -> None:
    driver = FakeTraceDriver()
    recorder = TraceRecorder(driver=driver)  # type: ignore[arg-type]

    await recorder.start(screenshots=True, snapshots=True)
    assert recorder.is_recording is True

    snap1 = PageSnapshot(
        timestamp=1700000000.0,
        device_id="test-device-1",
        viewport_width=1080,
        viewport_height=2400,
        elements=[
            CompactElement(ref="@1", role="button", text="确认", bounds=Rect(left=0, top=0, right=10, bottom=10))
        ],
    )

    await recorder.record_action(
        name="click",
        selector="text=确认",
        duration_ms=120,
        click_point=(5, 5),
        snapshot_before=snap1,
        snapshot_after=snap1,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = os.path.join(tmpdir, "test-trace.zip")
        out = await recorder.stop(path=trace_path)
        assert os.path.exists(out)

        # 检查 zip 内结构
        with zipfile.ZipFile(out, "r") as zf:
            namelist = zf.namelist()
            assert "manifest.json" in namelist
            assert "trace.trace" in namelist
            assert any(name.startswith("resources/") for name in namelist)


@pytest.mark.asyncio
async def test_device_and_page_tracing_integration() -> None:
    from phone_playwright.api.async_api import AsyncPhoneDevice

    driver = FakeTraceDriver()
    dev = AsyncPhoneDevice(driver=driver)  # type: ignore[arg-type]

    await dev.tracing.start(screenshots=True, snapshots=True)
    page = dev.current_page

    # 验证 page.locator.click() 自动触发 trace_recorder.record_action
    res = await page.locator("text=确认").click()
    assert res.success is True
    assert len(driver.taps) == 1
    # 命中节点中心 ( (100+300)//2, (200+400)//2 ) = (200, 300)
    assert driver.taps[0] == (200, 300)

    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = os.path.join(tmpdir, "integration-trace.zip")
        out = await dev.tracing.stop(path=trace_path)
        assert os.path.exists(out)
        with zipfile.ZipFile(out, "r") as zf:
            manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
            assert manifest_data["eventCount"] >= 1
            trace_lines = zf.read("trace.trace").decode("utf-8").strip().splitlines()
            assert len(trace_lines) >= 1
            action_event = json.loads(trace_lines[0])
            assert action_event["type"] == "action"
            assert action_event["name"] == "click"
            assert action_event["selector"] == "text=确认"
            assert action_event["click_point"] == {"x": 200, "y": 300}
