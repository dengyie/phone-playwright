"""Playwright 风格的 Actionability 状态机与动作引擎。

执行严密的动作可用性检查:
Attached (节点存在) -> Visible (视口内) -> Stable (坐标静止) -> Enabled (可交互) -> Dispatch (物理下发)。
在超时窗口内对进场动画施加等待，并在 fill 时执行 Playwright 规范的清空与重置语义，
全面支持 click, fill, hover (长按), wait_for (显式可见/隐藏状态断言等待)。
"""

from __future__ import annotations
import asyncio
import time
from typing import TYPE_CHECKING, Literal
from phone_playwright.models.geometry import Rect
from phone_playwright.models.actions import ActionResult
from phone_playwright.models.schema import CompactElement
from phone_playwright.models.exceptions import (
    ActionabilityTimeoutError,
    SelectorNotFoundError,
    OffscreenElementError,
)
from phone_playwright.core.selector import parse_selector

if TYPE_CHECKING:
    from phone_playwright.drivers.base import BaseDriver
    from phone_playwright.core.pruner import SemanticPruner


class ActionabilityEngine:
    """Actionability 状态机执行引擎。"""

    def __init__(
        self,
        driver: BaseDriver,
        pruner: SemanticPruner,
        poll_interval_s: float = 0.1,
        stable_sample_count: int = 1,
    ) -> None:
        self.driver = driver
        self.pruner = pruner
        self.poll_interval_s = poll_interval_s
        self.stable_sample_count = stable_sample_count
        self._cached_elements: list[CompactElement] | None = None
        self._cached_timestamp: float = 0.0

    def warm_cache(self, elements: list[CompactElement], timestamp: float) -> None:
        """为快照后紧随的动作执行预置短生命周期温热缓存 (TTL 1.0s)。"""
        self._cached_elements = elements
        self._cached_timestamp = timestamp

    def invalidate_cache(self) -> None:
        """显式清除温热缓存。"""
        self._cached_elements = None
        self._cached_timestamp = 0.0

    async def execute_action(
        self,
        verb: str,
        selector_str: str,
        value: str | None = None,
        timeout_s: float = 5.0,
        duration_ms: int = 800,
        expected_state: Literal["visible", "hidden"] = "visible",
        stable_sample_count: int | None = None,
    ) -> ActionResult:
        """对指定选择器目标执行具备可用性检查的操作。"""
        selector = parse_selector(selector_str)
        start_time = time.monotonic()
        last_bounds: Rect | None = None
        stable_hits = 0
        required_samples = stable_sample_count if stable_sample_count is not None else self.stable_sample_count

        vw, vh = await self.driver.get_viewport_size()
        viewport = Rect(left=0, top=0, right=vw, bottom=vh)

        # 针对 wait_for(state="hidden") 的快速分支处理
        if verb == "wait_for" and expected_state == "hidden":
            while time.monotonic() - start_time < timeout_s:
                try:
                    raw_tree = await self.driver.dump_raw_tree()
                    elements = self.pruner.prune_and_distill(raw_tree, vw, vh)
                except Exception:
                    await asyncio.sleep(self.poll_interval_s)
                    continue
                target_el = selector.find_first(elements)
                if not target_el or not target_el.bounds.intersects(viewport):
                    elapsed_ms = int((time.monotonic() - start_time) * 1000)
                    return ActionResult(
                        success=True,
                        verb="wait_for",
                        target=selector_str,
                        executed_at_bounds=None,
                        time_taken_ms=elapsed_ms,
                    )
                await asyncio.sleep(self.poll_interval_s)

            raise ActionabilityTimeoutError(
                selector=selector_str,
                timeout_s=timeout_s,
                details="目标元素在超时时间内持续可见，未能转变为隐藏状态",
            )

        # 常规可用性状态机主循环 (click / fill / hover / wait_for visible)
        is_first_iteration = True
        cur_elements: list[CompactElement] = []
        while time.monotonic() - start_time < timeout_s:
            now = time.monotonic()
            # 1. 尝试使用 1.0s 内的快照温热缓存 (仅首轮迭代生效，实现亚秒级极速首击)
            if is_first_iteration and self._cached_elements and (now - self._cached_timestamp < 1.0):
                cur_elements = self._cached_elements
            else:
                try:
                    raw_tree = await self.driver.dump_raw_tree()
                    cur_elements = self.pruner.prune_and_distill(raw_tree, vw, vh)
                except Exception:
                    await asyncio.sleep(self.poll_interval_s)
                    continue
            is_first_iteration = False

            # 2. Attached 检查：选择器是否匹配到节点
            target_el = selector.find_first(cur_elements)
            if not target_el:
                await asyncio.sleep(self.poll_interval_s)
                continue

            # 3. Visible & 视口检查：若由于进场动画导致暂未进入视口，继续等待
            inter = target_el.bounds.intersection(viewport)
            if inter is None or inter.width < 4 or inter.height < 4:
                stable_hits = 0
                await asyncio.sleep(self.poll_interval_s)
                continue

            # 4. Stable 检查：连续采样判定坐标是否静止 (防滑动/动画中点击)
            cur_bounds = target_el.bounds
            if last_bounds and cur_bounds == last_bounds:
                stable_hits += 1
            else:
                stable_hits = 1
            last_bounds = cur_bounds

            if stable_hits < required_samples:
                await asyncio.sleep(self.poll_interval_s)
                continue

            # 5. Enabled 检查 (对交互类动作生效)
            if verb in ("click", "fill", "hover") and not target_el.enabled:
                await asyncio.sleep(self.poll_interval_s)
                continue

            elapsed_ms = int((time.monotonic() - start_time) * 1000)

            # 针对 wait_for(state="visible")：元素稳定即可返回
            if verb == "wait_for":
                return ActionResult(
                    success=True,
                    verb="wait_for",
                    target=selector_str,
                    executed_at_bounds=cur_bounds,
                    time_taken_ms=elapsed_ms,
                )

            # 6. 计算安全物理中心坐标 (优先使用视口相交区域中心，防止部分出界导致点击越界) 并下发物理动作
            click_bounds = inter if inter is not None else target_el.bounds
            cx, cy = click_bounds.center
            self.invalidate_cache()

            if verb == "click":
                await self.driver.tap(cx, cy)
                return ActionResult(
                    success=True,
                    verb="click",
                    target=selector_str,
                    executed_at_bounds=cur_bounds,
                    time_taken_ms=elapsed_ms,
                )
            elif verb == "fill":
                # Playwright 契约：点击聚焦输入框 -> 清空 -> 注入新文本
                await self.driver.tap(cx, cy)
                await asyncio.sleep(0.05)
                clear_text = getattr(self.driver, "clear_text", None)
                if callable(clear_text):
                    try:
                        await clear_text()
                        await asyncio.sleep(0.05)
                    except Exception:
                        pass
                text_to_type = value or ""
                await self.driver.type_text(text_to_type)
                return ActionResult(
                    success=True,
                    verb="fill",
                    target=selector_str,
                    executed_at_bounds=cur_bounds,
                    time_taken_ms=elapsed_ms,
                )
            elif verb == "hover":
                # 触发长按 / 悬浮
                await self.driver.long_press(cx, cy, duration_ms=duration_ms)
                return ActionResult(
                    success=True,
                    verb="hover",
                    target=selector_str,
                    executed_at_bounds=cur_bounds,
                    time_taken_ms=elapsed_ms,
                )
            else:
                raise ValueError(f"不支持的动作动词: {verb}")

        # 最终超时后，精确定位超时原因 (包含异常屏障，防止末尾瞬态异常冲垮核心超时断言)
        try:
            raw_tree = await self.driver.dump_raw_tree()
            # 使用极大虚拟视口蒸馏未裁剪的完整节点树，精准区分【未挂载】与【屏幕外】
            unclipped_elements = self.pruner.prune_and_distill(raw_tree, 1000000, 1000000)
            target_node = selector.find_first(unclipped_elements)
            if not target_node:
                raise SelectorNotFoundError(selector_str)
            if not target_node.bounds.intersects(viewport):
                raise OffscreenElementError(selector_str)
        except (OffscreenElementError, SelectorNotFoundError):
            raise
        except Exception:
            pass

        raise ActionabilityTimeoutError(
            selector=selector_str,
            timeout_s=timeout_s,
            details=f"目标未能在规定时间内稳定就绪 (stable_hits={stable_hits})",
        )
