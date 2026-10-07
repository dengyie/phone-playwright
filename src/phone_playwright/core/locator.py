"""Playwright 风格的延迟定位器 (PhoneLocator)。"""

from __future__ import annotations
import asyncio
import time
from typing import TYPE_CHECKING, Literal
from phone_playwright.models.actions import ActionResult
from phone_playwright.models.geometry import Rect
from phone_playwright.models.schema import CompactElement
from phone_playwright.core.selector import parse_selector

if TYPE_CHECKING:
    from phone_playwright.api.async_api import AsyncPhonePage


class PhoneLocator:
    """延迟解析定位器，封装用户意图，每次执行时动态拉取最新状态。"""

    def __init__(self, page: AsyncPhonePage, selector: str) -> None:
        self._page = page
        self._selector = selector

    @property
    def selector(self) -> str:
        return self._selector

    async def click(self, timeout_s: float = 5.0, stable_sample_count: int | None = None) -> ActionResult:
        """Playwright 风格的 Auto-waiting click。"""
        return await self._page.action_engine.execute_action(
            verb="click",
            selector_str=self._selector,
            timeout_s=timeout_s,
            stable_sample_count=stable_sample_count,
        )

    async def fill(self, text: str, timeout_s: float = 5.0, stable_sample_count: int | None = None) -> ActionResult:
        """Playwright 风格的输入填充，内置自动聚焦。"""
        return await self._page.action_engine.execute_action(
            verb="fill",
            selector_str=self._selector,
            value=text,
            timeout_s=timeout_s,
            stable_sample_count=stable_sample_count,
        )

    async def hover(
        self, timeout_s: float = 5.0, duration_ms: int = 800, stable_sample_count: int | None = None
    ) -> ActionResult:
        """Playwright 风格的 hover (在移动端映射为长按唤起操作)。"""
        return await self._page.action_engine.execute_action(
            verb="hover",
            selector_str=self._selector,
            timeout_s=timeout_s,
            duration_ms=duration_ms,
            stable_sample_count=stable_sample_count,
        )

    async def wait_for(
        self, state: Literal["visible", "hidden"] = "visible", timeout_s: float = 5.0
    ) -> ActionResult:
        """显式断言等待元素状态变更 (visible 或 hidden)。"""
        return await self._page.action_engine.execute_action(
            verb="wait_for",
            selector_str=self._selector,
            timeout_s=timeout_s,
            expected_state=state,
        )

    async def _resolve_elements(self, force_refresh: bool = False) -> tuple[list[CompactElement], Rect]:
        """获取当前视口的元素列表与视口区域，优先复用 1.0s 内的快照/可用性引擎温热缓存。"""
        vw, vh = await self._page.driver.get_viewport_size()
        viewport = Rect(left=0, top=0, right=vw, bottom=vh)
        now = time.monotonic()
        engine = self._page.action_engine
        if not force_refresh and engine._cached_elements is not None and (now - engine._cached_timestamp < 1.0):
            return engine._cached_elements, viewport

        raw_tree = await self._page.driver.dump_raw_tree()
        elements = self._page.pruner.prune_and_distill(raw_tree, vw, vh)
        engine.warm_cache(elements, now)
        return elements, viewport

    async def scroll_into_view(
        self,
        max_swipes: int = 5,
        direction: Literal["up", "down"] = "up",
        distance_ratio: float = 0.5,
    ) -> PhoneLocator:
        """Playwright 风格的自动滚动搜寻: 若元素未在当前视口，自动向指定方向滑动直至可见。"""
        for _ in range(max_swipes):
            elements, viewport = await self._resolve_elements(force_refresh=True)
            target_el = parse_selector(self._selector).find_first(elements)
            if target_el and target_el.bounds.intersects(viewport):
                return self

            await self._page.swipe(direction=direction, distance_ratio=distance_ratio)
            await asyncio.sleep(0.4)

        return self

    async def is_visible(self) -> bool:
        """瞬态断言检查: 判断当前选择器目标是否处于视口内可见。"""
        try:
            elements, viewport = await self._resolve_elements()
            target = parse_selector(self._selector).find_first(elements)
            return bool(target and target.bounds.intersects(viewport))
        except Exception:
            return False

    async def count(self) -> int:
        """统计当前视口内命中该选择器的元素总数。"""
        try:
            elements, _ = await self._resolve_elements()
            sel = parse_selector(self._selector)
            return sum(1 for el in elements if sel.match(el))
        except Exception:
            return 0

    async def text_content(self) -> str | None:
        """获取目标元素关联的提取文本。"""
        try:
            elements, _ = await self._resolve_elements()
            target = parse_selector(self._selector).find_first(elements)
            return target.text if target else None
        except Exception:
            return None

    async def bounding_box(self) -> dict[str, int] | None:
        """获取目标元素在当前视口中的绝对物理坐标边界 {x, y, width, height}。"""
        try:
            elements, viewport = await self._resolve_elements()
            target = parse_selector(self._selector).find_first(elements)
            if target and target.bounds.intersects(viewport):
                b = target.bounds
                return {
                    "x": b.left,
                    "y": b.top,
                    "width": b.right - b.left,
                    "height": b.bottom - b.top,
                }
            return None
        except Exception:
            return None

