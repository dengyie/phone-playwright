"""AndroidAdbDriver 输入通道与旋转视口单元测试。"""

import pytest
from phone_playwright.drivers.android_adb import AndroidAdbDriver
from phone_playwright.models.exceptions import PhonePlaywrightError
from phone_playwright.models.geometry import Rect
from phone_playwright.models.schema import RawNode


class ScriptedAdbDriver(AndroidAdbDriver):
    """以脚本化输出替代真实 adb 子进程的测试驱动。"""

    def __init__(self) -> None:
        super().__init__(device_id="emulator-scripted")
        self.commands: list[tuple[str, ...]] = []
        self.responses: dict[str, str] = {}
        self.tree_texts: list[str] = []

    async def _run_adb(self, *args: str, timeout: float = 15.0) -> str:
        self.commands.append(tuple(args))
        return self.responses.get(" ".join(args), "")

    async def dump_raw_tree(self) -> RawNode:
        children = [
            RawNode(
                class_name="android.widget.EditText",
                text=text,
                bounds=Rect(left=0, top=0, right=100, bottom=50),
            )
            for text in self.tree_texts
        ]
        return RawNode(
            class_name="android.widget.FrameLayout",
            bounds=Rect(left=0, top=0, right=1600, bottom=900),
            children=children,
        )


@pytest.mark.asyncio
async def test_viewport_uses_current_rotation_size():
    driver = ScriptedAdbDriver()
    driver.responses["shell dumpsys window displays"] = (
        "Display: init=900x1600 240dpi cur=1600x900 app=1600x900 rng=900x864-1600x1564"
    )

    size = await driver.get_viewport_size()

    assert size == (1600, 900)


@pytest.mark.asyncio
async def test_viewport_falls_back_to_wm_size():
    driver = ScriptedAdbDriver()
    driver.responses["shell wm size"] = "Physical size: 1080x2400"

    size = await driver.get_viewport_size()

    assert size == (1080, 2400)


@pytest.mark.asyncio
async def test_type_text_ascii_uses_escaped_input_text():
    driver = ScriptedAdbDriver()

    await driver.type_text("hello world&")

    assert ("shell", "input", "text", "hello%sworld\\&") in driver.commands


@pytest.mark.asyncio
async def test_type_text_unicode_pastes_and_verifies_from_tree():
    driver = ScriptedAdbDriver()
    driver.tree_texts = ["无线局域网设置"]

    await driver.type_text("无线局域网设置")

    assert any("cmd clipboard" in " ".join(c) for c in driver.commands)
    paste_calls = [c for c in driver.commands if c == ("shell", "input", "keyevent", "279")]
    assert len(paste_calls) == 1


@pytest.mark.asyncio
async def test_type_text_unicode_raises_when_text_never_lands():
    driver = ScriptedAdbDriver()
    driver.tree_texts = []  # 校验始终找不到文本

    with pytest.raises(PhonePlaywrightError, match="未在界面树中检测到输入文本"):
        await driver.type_text("中文输入")

    # 通道正常的场景下应补发 Ctrl+V (CTRL_LEFT=113, V=47)
    assert ("shell", "input", "keycombination", "113", "47") in driver.commands


@pytest.mark.asyncio
async def test_type_text_unicode_no_ctrlv_retry_when_channel_unsupported():
    driver = ScriptedAdbDriver()
    driver.responses["shell cmd clipboard set text '无线局域网设置'"] = (
        "No shell command implementation."
    )
    driver.tree_texts = []

    with pytest.raises(PhonePlaywrightError, match="未在界面树中检测到输入文本"):
        await driver.type_text("无线局域网设置")

    # 通道未实现时不补发 Ctrl+V (避免把宿主剪贴板旧内容重复粘入)
    assert ("shell", "input", "keycombination", "113", "47") not in driver.commands
