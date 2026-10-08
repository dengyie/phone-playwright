"""异步 SDK API 门面 (Async API)。

提供标准 Playwright 风格的类与接口:
AsyncPhonePlaywright -> AsyncPhoneDevice -> AsyncPhonePage -> PhoneLocator
支持无障碍树优先、轻量 OCR 视觉按需兜底的混合感知能力。
"""

from __future__ import annotations
import base64
import time
from typing import Any, AsyncIterator, Literal
from phone_playwright.drivers.base import BaseDriver
from phone_playwright.core.pruner import SemanticPruner
from phone_playwright.core.state_machine import ActionabilityEngine
from phone_playwright.core.locator import PhoneLocator
from phone_playwright.core.vision import RapidOcrFallbackProvider
from phone_playwright.core.som import SetOfMarkRenderer
from phone_playwright.core.gesture import GestureEngine
from phone_playwright.core.cdp import WebFrameLocator
from phone_playwright.tracing.recorder import TraceRecorder
from phone_playwright.models.schema import PageSnapshot
from phone_playwright.fleet.manager import FleetManager


class AsyncPhonePage:
    """当前移动设备屏幕页面操作实例。"""

    def __init__(
        self,
        driver: BaseDriver,
        pruner: SemanticPruner,
        tracing: TraceRecorder | None = None,
    ) -> None:
        self.driver = driver
        self.pruner = pruner
        self.tracing = tracing or TraceRecorder(driver=driver)
        self.action_engine = ActionabilityEngine(
            driver=driver,
            pruner=pruner,
            trace_recorder=self.tracing,
        )
        self.vision_fallback = RapidOcrFallbackProvider()
        self.som_renderer = SetOfMarkRenderer()
        self.gesture_engine = GestureEngine(driver=driver)

    def __call__(self) -> AsyncPhonePage:
        """支持 device.current_page() 函数式调用习惯。"""
        return self

    async def snapshot(
        self,
        use_vision_fallback: bool = False,
        include_screenshot: bool = False,
        include_som_image: bool = False,
        som_palette: dict[str, str] | None = None,
    ) -> PageSnapshot:
        """拉取当前屏幕视口内的紧凑无障碍语义快照。

        若提取到的无障碍元素极度稀疏 (<= 2) 或调用方显式指定，自动触发视觉 OCR 兜底补充。
        若 include_screenshot 为 True，抓取截图并填充 screenshot_base64 字段。
        若 include_som_image 为 True，生成 Set-of-Mark 标注图并填充 annotated_screenshot_base64 字段。
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

        need_screenshot = include_screenshot or include_som_image
        if need_screenshot and shot_bytes is None:
            try:
                shot_bytes = await self.driver.take_screenshot()
            except Exception:
                pass

        screenshot_b64: str | None = None
        annotated_b64: str | None = None
        if shot_bytes is not None:
            if include_screenshot:
                screenshot_b64 = base64.b64encode(shot_bytes).decode("ascii")
            if include_som_image:
                try:
                    annotated_b64 = self.som_renderer.render_som_base64(
                        image_bytes=shot_bytes,
                        elements=elements,
                        viewport_width=vw,
                        viewport_height=vh,
                        palette_override=som_palette,
                    )
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
            annotated_screenshot_base64=annotated_b64,
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

    def get_by_test_id(self, test_id: str) -> PhoneLocator:
        """快捷定位器: 按资源 ID / 测试 ID 定位。"""
        return self.locator(f"id={test_id}")

    def frame_locator(self, selector: str = "role=scrollable") -> WebFrameLocator:
        """根据原生选择器定位内嵌 WebView 容器，并返回内嵌 Web 树定位器。"""
        return WebFrameLocator(page=self, container_selector=selector)

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

    async def pinch_out(
        self,
        center: tuple[int, int] | None = None,
        scale: float = 2.0,
        duration_ms: int = 400,
    ) -> None:
        """双指张开 (放大): 两指从中心向外平滑对称滑动。"""
        self.action_engine.invalidate_cache()
        if center is None:
            vw, vh = await self.driver.get_viewport_size()
            center = (vw // 2, vh // 2)
        await self.gesture_engine.pinch(center=center, scale=scale, duration_ms=duration_ms)

    async def pinch_in(
        self,
        center: tuple[int, int] | None = None,
        scale: float = 0.5,
        duration_ms: int = 400,
    ) -> None:
        """双指捏合 (缩小): 两指从外侧向中心平滑对称滑动。"""
        self.action_engine.invalidate_cache()
        if center is None:
            vw, vh = await self.driver.get_viewport_size()
            center = (vw // 2, vh // 2)
        await self.gesture_engine.pinch(center=center, scale=scale, duration_ms=duration_ms)

    async def swipe_path(
        self,
        points: list[tuple[int, int]],
        duration_ms: int = 800,
    ) -> None:
        """多点折线连续手势 (如九宫格锁屏、复杂滑块拼图)。"""
        self.action_engine.invalidate_cache()
        await self.gesture_engine.swipe_path(points=points, duration_ms=duration_ms)

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
        self.tracing = TraceRecorder(driver=driver)
        self._current_page = AsyncPhonePage(
            driver=driver,
            pruner=self.pruner,
            tracing=self.tracing,
        )

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

    def frame_locator(self, selector: str = "role=scrollable") -> WebFrameLocator:
        return self._current_page.frame_locator(selector)

    async def snapshot(
        self,
        use_vision_fallback: bool = False,
        include_screenshot: bool = False,
        include_som_image: bool = False,
        som_palette: dict[str, str] | None = None,
    ) -> PageSnapshot:
        return await self._current_page.snapshot(
            use_vision_fallback=use_vision_fallback,
            include_screenshot=include_screenshot,
            include_som_image=include_som_image,
            som_palette=som_palette,
        )

    async def swipe(
        self,
        direction: Literal["up", "down", "left", "right"],
        distance_ratio: float = 0.5,
    ) -> None:
        await self._current_page.swipe(direction=direction, distance_ratio=distance_ratio)

    async def pinch_out(
        self,
        center: tuple[int, int] | None = None,
        scale: float = 2.0,
        duration_ms: int = 400,
    ) -> None:
        await self._current_page.pinch_out(center=center, scale=scale, duration_ms=duration_ms)

    async def pinch_in(
        self,
        center: tuple[int, int] | None = None,
        scale: float = 0.5,
        duration_ms: int = 400,
    ) -> None:
        await self._current_page.pinch_in(center=center, scale=scale, duration_ms=duration_ms)

    async def swipe_path(
        self,
        points: list[tuple[int, int]],
        duration_ms: int = 800,
    ) -> None:
        await self._current_page.swipe_path(points=points, duration_ms=duration_ms)

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
