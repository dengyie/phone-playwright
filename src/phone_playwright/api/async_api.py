"""异步 SDK API 门面 (Async API)。

提供标准 Playwright 风格的类与接口:
AsyncPhonePlaywright -> AsyncPhoneDevice -> AsyncPhonePage -> PhoneLocator
支持无障碍树优先、轻量 OCR 视觉按需兜底的混合感知能力。
"""

from __future__ import annotations
import base64
import time
from typing import AsyncIterator, Literal
from phone_playwright.drivers.base import BaseDriver
from phone_playwright.core.pruner import SemanticPruner
from phone_playwright.core.state_machine import ActionabilityEngine
from phone_playwright.core.locator import PhoneLocator
from phone_playwright.core.vision import RapidOcrFallbackProvider
from phone_playwright.models.schema import PageSnapshot
from phone_playwright.fleet.manager import FleetManager


class AsyncPhonePage:
    """当前移动设备屏幕页面操作实例。"""

    def __init__(self, driver: BaseDriver, pruner: SemanticPruner) -> None:
        self.driver = driver
        self.pruner = pruner
        self.action_engine = ActionabilityEngine(driver=driver, pruner=pruner)
        self.vision_fallback = RapidOcrFallbackProvider()

    def __call__(self) -> AsyncPhonePage:
        """支持 device.current_page() 函数式调用习惯。"""
        return self

    async def snapshot(
        self,
        use_vision_fallback: bool = False,
        include_screenshot: bool = False,
    ) -> PageSnapshot:
        """拉取当前屏幕视口内的紧凑无障碍语义快照。

        若提取到的无障碍元素极度稀疏 (<= 2) 或调用方显式指定，自动触发视觉 OCR 兜底补充。
        若 include_screenshot 为 True，抓取截图并填充 screenshot_base64 字段。
        """
        vw, vh = await self.driver.get_viewport_size()
        raw_tree = await self.driver.dump_raw_tree()
        elements = self.pruner.prune_and_distill(raw_tree, vw, vh)
        pkg, act = await self.driver.get_current_app()

        shot_bytes: bytes | None = None
        # 触发视觉兜底策略：无障碍失明或显式请求
        if (len(elements) <= 2 or use_vision_fallback) and self.vision_fallback.is_available:
            try:
                shot_bytes = await self.driver.take_screenshot()
                vision_elements = self.vision_fallback.recognize_text_blocks(shot_bytes, vw, vh)
                if vision_elements:
                    elements.extend(vision_elements)
            except Exception:
                pass

        screenshot_b64: str | None = None
        if include_screenshot:
            try:
                if shot_bytes is None:
                    shot_bytes = await self.driver.take_screenshot()
                screenshot_b64 = base64.b64encode(shot_bytes).decode("ascii")
            except Exception:
                pass

        # 为紧随其后的即时 locator 交互预热缓存 (TTL 1.0s)
        self.action_engine.warm_cache(elements, time.monotonic())

        return PageSnapshot(
            timestamp=time.time(),
            device_id=self.driver.device_id,
            package_name=pkg,
            activity_name=act,
            viewport_width=vw,
            viewport_height=vh,
            elements=elements,
            screenshot_base64=screenshot_b64,
        )

    def locator(self, selector: str) -> PhoneLocator:
        """创建 Playwright 风格的延迟定位器。"""
        return PhoneLocator(page=self, selector=selector)

    def get_by_text(self, text: str, exact: bool = False) -> PhoneLocator:
        """语义快捷定位器: 按文本定位。"""
        prefix = "exact:text=" if exact else "text="
        return self.locator(f"{prefix}{text}")

    def get_by_role(self, role: str, name: str | None = None) -> PhoneLocator:
        """语义快捷定位器: 按无障碍角色与标签定位。"""
        sel = f"role={role}[name={name}]" if name else f"role={role}"
        return self.locator(sel)

    async def screenshot(self) -> bytes:
        """抓取物理屏幕图像数据。"""
        return await self.driver.take_screenshot()

    async def dump_raw_tree(self) -> Any:
        """导出物理设备原始树层级。"""
        return await self.driver.dump_raw_tree()

    async def swipe(
        self,
        *args: Any,
        direction: Literal["up", "down", "left", "right"] | None = None,
        distance_ratio: float = 0.5,
        **kwargs: Any,
    ) -> None:
        """支持方向滑动与两点绝对坐标滑动。"""
        self.action_engine.invalidate_cache()
        if len(args) >= 4 or {"start_x", "start_y", "end_x", "end_y"}.issubset(kwargs):
            sx = int(args[0]) if len(args) >= 1 else int(kwargs["start_x"])
            sy = int(args[1]) if len(args) >= 2 else int(kwargs["start_y"])
            ex = int(args[2]) if len(args) >= 3 else int(kwargs["end_x"])
            ey = int(args[3]) if len(args) >= 4 else int(kwargs["end_y"])
            dur = args[4] if len(args) >= 5 else kwargs.get("duration", 0.3)
            duration_ms = int(float(dur) * 1000) if float(dur) <= 10 else int(dur)
            await self.driver.swipe(sx, sy, ex, ey, duration_ms=duration_ms)
            return

        resolved_dir = direction or (args[0] if len(args) >= 1 and isinstance(args[0], str) else None)
        if resolved_dir is None:
            raise ValueError("必须指定滑动方向或起止坐标")

        resolved_ratio = float(args[1]) if len(args) >= 2 else distance_ratio

        vw, vh = await self.driver.get_viewport_size()
        cx = vw // 2
        cy = vh // 2
        delta_y = int(vh * resolved_ratio // 2)
        delta_x = int(vw * resolved_ratio // 2)

        if resolved_dir == "up":
            await self.driver.swipe(cx, cy + delta_y, cx, cy - delta_y)
        elif resolved_dir == "down":
            await self.driver.swipe(cx, cy - delta_y, cx, cy + delta_y)
        elif resolved_dir == "left":
            await self.driver.swipe(cx + delta_x, cy, cx - delta_x, cy)
        elif resolved_dir == "right":
            await self.driver.swipe(cx - delta_x, cy, cx + delta_x, cy)
        else:
            raise ValueError(f"不支持的滑动方向: {resolved_dir}")

    async def press_key(self, key: str | int) -> None:
        """模拟物理或系统按键。"""
        self.action_engine.invalidate_cache()
        await self.driver.press_key(key)

    async def press_back(self) -> None:
        """模拟系统返回键。"""
        self.action_engine.invalidate_cache()
        await self.driver.press_back()

    async def press_home(self) -> None:
        """模拟系统物理 Home 键返回桌面。"""
        self.action_engine.invalidate_cache()
        await self.driver.press_home()


class AsyncPhoneDevice:
    """移动设备控制句柄。"""

    def __init__(self, driver: BaseDriver) -> None:
        self.driver = driver
        self.pruner = SemanticPruner()
        self._current_page = AsyncPhonePage(driver=driver, pruner=self.pruner)

    @property
    def current_page(self) -> AsyncPhonePage:
        return self._current_page

    @property
    def page(self) -> AsyncPhonePage:
        return self._current_page

    def locator(self, selector: str) -> PhoneLocator:
        return self._current_page.locator(selector)

    def get_by_text(self, text: str, exact: bool = False) -> PhoneLocator:
        return self._current_page.get_by_text(text, exact=exact)

    def get_by_role(self, role: str, name: str | None = None) -> PhoneLocator:
        return self._current_page.get_by_role(role, name=name)

    def get_by_test_id(self, test_id: str) -> PhoneLocator:
        return self._current_page.get_by_test_id(test_id)

    async def snapshot(
        self,
        use_vision_fallback: bool = False,
        include_screenshot: bool = False,
    ) -> PageSnapshot:
        return await self._current_page.snapshot(
            use_vision_fallback=use_vision_fallback,
            include_screenshot=include_screenshot,
        )

    async def swipe(
        self,
        direction: Literal["up", "down", "left", "right"],
        distance_ratio: float = 0.5,
    ) -> None:
        await self._current_page.swipe(direction=direction, distance_ratio=distance_ratio)

    async def press_back(self) -> None:
        await self._current_page.press_back()

    async def press_home(self) -> None:
        await self._current_page.press_home()


class AsyncPhonePlaywright:
    """顶级 Playwright 上下文管理器。"""

    def __init__(self, adb_path: str = "adb") -> None:
        self.fleet = FleetManager(adb_path=adb_path)

    async def __aenter__(self) -> AsyncPhonePlaywright:
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        await self.fleet.close_all()

    async def connect(self, alias_or_id: str = "", device_id: str = "") -> AsyncPhoneDevice:
        """连接目标设备并返回设备句柄。"""
        target = device_id or alias_or_id
        driver = await self.fleet.get_driver(target)
        return AsyncPhoneDevice(driver=driver)

    async def list_devices(self) -> list[dict[str, str]]:
        return await self.fleet.scan_devices()


def async_phone_playwright(adb_path: str = "adb") -> AsyncPhonePlaywright:
    """构建异步 Playwright 上下文工厂。"""
    return AsyncPhonePlaywright(adb_path=adb_path)
