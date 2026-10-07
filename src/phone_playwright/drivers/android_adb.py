"""Android 平台原生 ADB 驱动实现。

采用高性能 asyncio.subprocess 直接桥接本地 ADB。
支持完整 XML 原始转译为统一 RawNode（虚拟根容器支持多窗口与 Dialog），
支持安全转义文本输入、绝对像素点击、手势滑动与视口截图。
"""

from __future__ import annotations
import asyncio
import base64
import re
import shlex
import time
import xml.etree.ElementTree as ET
from phone_playwright.drivers.base import BaseDriver
from phone_playwright.models.geometry import Rect
from phone_playwright.models.schema import RawNode
from phone_playwright.models.exceptions import DeviceOfflineError, PhonePlaywrightError


_ANDROID_KEYCODES: dict[str, int] = {
    "home": 3,
    "back": 4,
    "volume_up": 24,
    "volume_down": 25,
    "power": 26,
    "tab": 61,
    "enter": 66,
    "del": 67,
    "delete": 67,
    "backspace": 67,
    "menu": 82,
    "search": 84,
}

# 部分 ROM / 云手机 (如 MuMu) 对未实现的 shell 子命令返回 rc=0 + 提示文本,
# 必须按输出内容判定剪贴板通道不可用, 否则注入会静默空转。
_CLIPBOARD_UNSUPPORTED_MARKERS: tuple[str, ...] = (
    "no shell command implementation",
    "unknown command",
    "not implemented",
    "bad usage",
    "usage: ",
)

_ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"


class AndroidAdbDriver(BaseDriver):
    """基于 ADB 的 Android 驱动实现。"""

    _VIEWPORT_CACHE_TTL_S: float = 1.0

    def __init__(self, device_id: str, adb_path: str = "adb") -> None:
        super().__init__(device_id)
        self.adb_path = adb_path
        self._cached_viewport: tuple[int, int] | None = None
        self._cached_viewport_at: float = 0.0
        self._original_ime: str | None = None
        self._current_ime: str | None = None
        self._adb_ime_checked: bool = False
        self._adb_ime_available: bool = False

    def _cmd_prefix(self) -> list[str]:
        if self.device_id:
            return [self.adb_path, "-s", self.device_id]
        return [self.adb_path]

    async def _run_adb(self, *args: str, timeout: float = 15.0) -> str:
        cmd = [*self._cmd_prefix(), *args]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise DeviceOfflineError(self.device_id, f"ADB 命令执行超时: {' '.join(cmd)}")

        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            # 区分设备物理离线与普通命令异常
            # ('not found' 需兼容 "device '192.168.1.3:43037' not found" 这类带引号序列号的形态)
            offline_patterns = ("device offline", "device not found", "not found", "connection refused", "cannot connect", "offline")
            if any(p in err_msg.lower() for p in offline_patterns):
                raise DeviceOfflineError(self.device_id, f"ADB 传输通道离线 ({proc.returncode}): {err_msg}")
            raise PhonePlaywrightError(
                message=f"ADB 命令执行失败 ({proc.returncode}): {err_msg}",
                suggestion="请检查命令参数与当前系统状态",
            )

        return stdout.decode("utf-8", errors="replace").strip()

    async def connect(self) -> None:
        """测试连接可用性并初始化视口大小。"""
        if not self.device_id:
            proc = await asyncio.create_subprocess_exec(
                self.adb_path, "devices",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await proc.communicate()
            for line in out.decode().splitlines()[1:]:
                parts = line.strip().split()
                if len(parts) >= 2 and parts[1] == "device":
                    self.device_id = parts[0]
                    break

        if ":" in self.device_id:
            await asyncio.create_subprocess_exec(
                self.adb_path, "connect", self.device_id,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        await self.get_viewport_size()

    async def disconnect(self) -> None:
        """释放资源 (清理本地句柄，还原输入法，不对全局 adb server 执行强硬断开以保护多会话)。"""
        self._cached_viewport = None
        if self._original_ime and self._current_ime == _ADB_KEYBOARD_IME:
            try:
                await self._run_adb("shell", "ime", "set", self._original_ime)
                self._current_ime = self._original_ime
            except Exception:
                pass

    async def _ensure_adb_ime(self) -> bool:
        """检查并确保 AdbIME 处于激活状态，支持自动切换与退出还原。"""
        if not self._adb_ime_checked:
            try:
                imes = await self._run_adb("shell", "ime", "list", "-a")
                self._adb_ime_available = _ADB_KEYBOARD_IME.split("/")[0] in imes
            except Exception:
                self._adb_ime_available = False
            self._adb_ime_checked = True

        if not self._adb_ime_available:
            return False

        if self._current_ime != _ADB_KEYBOARD_IME:
            try:
                cur = await self._run_adb("shell", "settings", "get", "secure", "default_input_method")
                if cur and "/" in cur and not self._original_ime:
                    self._original_ime = cur.strip()
                await self._run_adb("shell", "ime", "enable", _ADB_KEYBOARD_IME)
                await self._run_adb("shell", "ime", "set", _ADB_KEYBOARD_IME)
                self._current_ime = _ADB_KEYBOARD_IME
            except Exception:
                return False
        return True

    async def _type_via_adb_ime(self, text: str) -> bool:
        """通道 2: 基于 AdbIME 广播通道注入 UTF-8 / Base64 文本。"""
        if not await self._ensure_adb_ime():
            return False
        b64_str = base64.b64encode(text.encode("utf-8")).decode("ascii")
        try:
            await self._run_adb("shell", "am", "broadcast", "-a", "ADB_INPUT_B64", "--es", "msg", b64_str)
            await asyncio.sleep(0.3)
            return True
        except Exception:
            return False

    async def get_viewport_size(self) -> tuple[int, int]:
        now = time.monotonic()
        if self._cached_viewport and (now - self._cached_viewport_at < self._VIEWPORT_CACHE_TTL_S):
            return self._cached_viewport

        # 优先读取当前旋转下的真实应用空间尺寸 (cur=WxH)。
        # wm size 返回的是未旋转物理面板 (init=)，横屏/模拟器旋转时会与
        # 无障碍树坐标系相差 90°，导致蒸馏裁剪与方向滑动的几何全部错位。
        try:
            display_info = await self._run_adb("shell", "dumpsys", "window", "displays", timeout=8.0)
            match = re.search(r"cur=(\d+)x(\d+)", display_info)
            if match:
                size = (int(match.group(1)), int(match.group(2)))
                self._cached_viewport = size
                self._cached_viewport_at = now
                return size
        except Exception:
            pass

        output = await self._run_adb("shell", "wm", "size")
        # 优先解析 Override size (模拟器/云手机常强制逻辑分辨率)，其优先级高于
        # 未旋转的 Physical size；两者顺序无关地按关键字匹配，避免 re.search 取到
        # 首行的物理尺寸而对横屏/缩放设备给出错误视口。
        override = re.search(r"Override size:\s*(\d+)x(\d+)", output)
        physical = re.search(r"Physical size:\s*(\d+)x(\d+)", output)
        match = override or physical
        size = (int(match.group(1)), int(match.group(2))) if match else (1080, 2400)
        self._cached_viewport = size
        self._cached_viewport_at = now
        return size

    async def dump_raw_tree(self) -> RawNode:
        """从手机 dump UI 层次结构并解析为 RawNode 多叉树。"""
        await self._run_adb("shell", "uiautomator", "dump", "/data/local/tmp/uidump.xml")
        xml_content = await self._run_adb("shell", "cat", "/data/local/tmp/uidump.xml")

        if not xml_content.startswith("<?xml") and not xml_content.startswith("<hierarchy"):
            raise ValueError(f"拉取到的 UI XML 格式异常: {xml_content[:100]}")

        vw, vh = await self.get_viewport_size()
        return parse_android_xml_hierarchy(xml_content, default_width=vw, default_height=vh)

    async def tap(self, x: int, y: int) -> None:
        await self._run_adb("shell", "input", "tap", str(x), str(y))

    async def clear_text(self) -> None:
        """清空当前焦点输入框内容，供 fill 的替换语义使用。

        采用 MOVE_END + 连续 DEL，不依赖 CTRL+A 组合键 —— 部分 ROM/模拟器
        (如实测的 MuMu) 的 keycombination 不携带 CTRL 修饰，会退化为单字符
        输入反而污染输入框。空字段上的 DEL 为无操作，代价可忽略。
        """
        keycodes = ["123"] + ["67"] * 100
        await self._run_adb("shell", "input", "keyevent", *keycodes)

    async def type_text(self, text: str) -> None:
        """安全键入文本。具备三通道自愈阶梯 (Tri-Channel Input Fallback Chain)。"""
        if not text:
            return

        has_non_ascii = any(ord(c) > 127 for c in text)
        if has_non_ascii:
            # 优先尝试通道 1: 剪贴板 + KEYCODE_PASTE (279)
            clipboard_failed = False
            safe_text = shlex.quote(text)
            try:
                response = await self._run_adb("shell", f"cmd clipboard set text {safe_text}")
                lowered = response.lower()
                unsupported = any(marker in lowered for marker in _CLIPBOARD_UNSUPPORTED_MARKERS)
                if not unsupported:
                    await self._run_adb("shell", "input", "keyevent", "279")
                    await asyncio.sleep(0.3)
                    if await self._tree_contains_text(text):
                        return
                    # 尝试 Ctrl+V 组合键补发
                    try:
                        await self._run_adb("shell", "input", "keycombination", "113", "47")
                        await asyncio.sleep(0.3)
                        if await self._tree_contains_text(text):
                            return
                    except Exception:
                        pass
                clipboard_failed = True
            except Exception:
                clipboard_failed = True

            # 剪贴板失败或不可用，自动降级到通道 2: AdbIME 广播通道 (ADB_INPUT_B64)
            if clipboard_failed or unsupported:
                success_ime = await self._type_via_adb_ime(text)
                if success_ime and await self._tree_contains_text(text):
                    return

            raise PhonePlaywrightError(
                "非 ASCII 文本注入失败 (剪贴板通道与 AdbIME 广播通道均未能成功写入目标输入框)",
                suggestion=(
                    "请确认焦点已正确位于可编辑输入框内，或检查设备是否预装并启用了 ADBKeyBoard 输入法"
                ),
            )

        # 安全 ASCII 字符注入路径：严格对每个字符做输入法转义 (空格 -> %s, Shell 元字符 -> 反斜杠转义)

        # 安全 ASCII 字符注入路径：严格对每个字符做输入法转义 (空格 -> %s, Shell 元字符 -> 反斜杠转义)
        tokens: list[str] = []
        for ch in text:
            if ch == " ":
                tokens.append("%s")
            elif ch in "'\"&;()<>$`\\|*?!#~[]{}":
                tokens.append(f"\\{ch}")
            else:
                tokens.append(ch)
        escaped_arg = "".join(tokens)
        await self._run_adb("shell", "input", "text", escaped_arg)

    async def _tree_contains_text(self, payload: str) -> bool:
        """在当前无障碍原始树中检索目标文本 (用于注入终态校验)。"""
        try:
            tree = await self.dump_raw_tree()
        except Exception:
            return False
        stack: list[RawNode] = [tree]
        while stack:
            node = stack.pop()
            if (node.text and payload in node.text) or (node.desc and payload in node.desc):
                return True
            stack.extend(node.children)
        return False

    async def swipe(self, sx: int, sy: int, ex: int, ey: int, duration_ms: int = 300) -> None:
        await self._run_adb(
            "shell", "input", "swipe", str(sx), str(sy), str(ex), str(ey), str(duration_ms)
        )

    async def long_press(self, x: int, y: int, duration_ms: int = 800) -> None:
        """物理长按绝对像素坐标 (基于原地微小滑动模拟长按)。"""
        await self._run_adb(
            "shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration_ms)
        )

    async def press_key(self, key: str | int) -> None:
        """触发 Android Keyevent 按键。"""
        if isinstance(key, int):
            keycode = key
        elif str(key).isdigit():
            keycode = int(key)
        else:
            k = str(key).lower().strip()
            if k not in _ANDROID_KEYCODES:
                raise ValueError(f"未知的 Android 按键标识: {key}")
            keycode = _ANDROID_KEYCODES[k]
        await self._run_adb("shell", "input", "keyevent", str(keycode))

    async def take_screenshot(self) -> bytes:
        # 1. 尝试首选的高性能 exec-out screencap -p (支持 1 次微重试)
        for attempt in range(2):
            try:
                proc = await asyncio.create_subprocess_exec(
                    *self._cmd_prefix(), "exec-out", "screencap", "-p",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=8.0)
                if proc.returncode == 0 and len(stdout) > 0:
                    return stdout
            except (asyncio.TimeoutError, Exception):
                pass
            if attempt == 0:
                await asyncio.sleep(0.2)

        # 2. 降级方案：写入临时文件并读取 (兼容转场锁帧或某些定制 Rom 的 exec-out 异常)
        tmp_remote = "/data/local/tmp/pp_screenshot.png"
        try:
            await self._run_adb("shell", "screencap", "-p", tmp_remote, timeout=10.0)
            proc = await asyncio.create_subprocess_exec(
                *self._cmd_prefix(), "exec-out", "cat", tmp_remote,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            if proc.returncode == 0 and len(stdout) > 0:
                return stdout
        except Exception as fallback_exc:
            raise PhonePlaywrightError(
                f"截屏执行失败 (exec-out 与文件降级均未成功: {fallback_exc})"
            ) from fallback_exc

        raise PhonePlaywrightError("截屏执行失败: 设备未返回有效图像数据")

    async def get_current_app(self) -> tuple[str | None, str | None]:
        try:
            output = await self._run_adb("shell", "dumpsys", "window", "displays")
            match = re.search(r"mCurrentFocus=Window\{[^\}]+\s+([^\s/]+)/([^\s\}]+)\}", output)
            if match:
                return match.group(1), match.group(2)
        except Exception:
            pass
        return None, None


def _parse_bounds_str(bounds_str: str) -> Rect:
    """解析形如 '[0,0][1080,2400]' 或包含负数坐标 '[-50,100][500,300]' 的 Android 坐标串。"""
    match = re.match(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", bounds_str)
    if not match:
        return Rect(left=0, top=0, right=0, bottom=0)
    return Rect(
        left=int(match.group(1)),
        top=int(match.group(2)),
        right=int(match.group(3)),
        bottom=int(match.group(4)),
    )


# 类名可能不直接含 "edit" 的可编辑控件。
# "edittext" 覆盖 EditText / AppCompatEditText / TextInputEditText / ExtractEditText 等；
# "autocompletetextview" 覆盖 AutoCompleteTextView / MultiAutoCompleteTextView 等；
# "searchautocomplete" 覆盖 SearchAutoComplete (SearchView 内嵌)。
_EDITABLE_CLASS_MARKERS = (
    "edittext",
    "autocompletetextview",
    "searchautocomplete",
)


def _is_editable_class(class_name: str) -> bool:
    """判定控件类名是否属于可编辑输入控件。

    不能只查 "edit" 子串 —— 三星 SearchView 的真实输入控件类名是
    android.widget.AutoCompleteTextView (不含 "edit")，会导致输入框漏判，
    使 fill / role=input 无法定位到该字段。
    """
    cls_lower = class_name.lower()
    return any(marker in cls_lower for marker in _EDITABLE_CLASS_MARKERS)


def parse_android_xml_hierarchy(
    xml_text: str, default_width: int = 1080, default_height: int = 2400
) -> RawNode:
    """将 Android 原生 uiautomator dump XML 转换为统一 RawNode。

    通过虚拟根节点挂载所有同级窗口与弹窗节点，彻底解决多窗口与 Dialog 被截断丢失的问题。
    """
    root_element = ET.fromstring(xml_text)

    def _convert_node(elem: ET.Element) -> RawNode:
        bounds_rect = _parse_bounds_str(elem.attrib.get("bounds", "[0,0][0,0]"))
        node = RawNode(
            resource_id=elem.attrib.get("resource-id", ""),
            class_name=elem.attrib.get("class", elem.tag),
            text=elem.attrib.get("text") or None,
            desc=elem.attrib.get("content-desc") or None,
            bounds=bounds_rect,
            clickable=elem.attrib.get("clickable", "false").lower() == "true",
            editable=_is_editable_class(elem.attrib.get("class", "")),
            scrollable=elem.attrib.get("scrollable", "false").lower() == "true",
            checkable=elem.attrib.get("checkable", "false").lower() == "true",
            enabled=elem.attrib.get("enabled", "true").lower() == "true",
            visible=elem.attrib.get("visibility", "visible").lower() in ("visible", ""),
        )
        for child_elem in elem:
            node.children.append(_convert_node(child_elem))
        return node

    # 若根节点为 <hierarchy>，建立全局虚拟视口根容器，收集并保留其下全部子窗口 (如 Dialog、浮层)
    if root_element.tag == "hierarchy":
        virtual_root = RawNode(
            resource_id="hierarchy:root",
            class_name="android.widget.FrameLayout",
            bounds=Rect(left=0, top=0, right=default_width, bottom=default_height),
            clickable=False,
            editable=False,
            enabled=True,
            visible=True,
        )
        for child_elem in root_element:
            virtual_root.children.append(_convert_node(child_elem))
        return virtual_root

    return _convert_node(root_element)
