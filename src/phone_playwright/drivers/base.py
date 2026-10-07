"""硬件驱动抽象基类 (BaseDriver)。

隔离 Android / iOS 物理差异，约束统一的 I/O 通信契约。
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from phone_playwright.models.schema import RawNode


class BaseDriver(ABC):
    """跨平台移动端驱动基类。"""

    def __init__(self, device_id: str) -> None:
        self.device_id = device_id

    @abstractmethod
    async def connect(self) -> None:
        """建立底层通信通道。"""

    @abstractmethod
    async def disconnect(self) -> None:
        """释放底层网络或 RPC 资源。"""

    @abstractmethod
    async def get_viewport_size(self) -> tuple[int, int]:
        """获取物理分辨率视口 (width, height)。"""

    @abstractmethod
    async def dump_raw_tree(self) -> RawNode:
        """拉取当前屏幕原始树并转译为 RawNode 多叉树。"""

    @abstractmethod
    async def tap(self, x: int, y: int) -> None:
        """物理点击绝对像素坐标。"""

    @abstractmethod
    async def type_text(self, text: str) -> None:
        """键入文本字符串。"""

    @abstractmethod
    async def swipe(self, sx: int, sy: int, ex: int, ey: int, duration_ms: int = 300) -> None:
        """执行绝对像素滑动。"""

    @abstractmethod
    async def long_press(self, x: int, y: int, duration_ms: int = 800) -> None:
        """物理长按绝对像素坐标 (用于 Hover / 上下文菜单)。"""

    @abstractmethod
    async def press_key(self, key: str | int) -> None:
        """触发物理/系统按键 (如 'back', 'home', 'enter' 或数字键码)。"""

    async def press_back(self) -> None:
        """模拟物理返回键。"""
        await self.press_key("back")

    async def press_home(self) -> None:
        """模拟物理 Home 键返回主屏幕。"""
        await self.press_key("home")

    @abstractmethod
    async def take_screenshot(self) -> bytes:
        """截取当前屏幕二进制图像数据 (PNG/JPEG)。"""

    @abstractmethod
    async def get_current_app(self) -> tuple[str | None, str | None]:
        """获取当前活跃应用的 (package_name, activity_name)。"""
