"""Playwright 风格的异步/同步断言库 (Expect Engine)。

对齐规格书: docs/specs/06-expect-assertions-and-trace.md
针对移动端网络延迟、转场动画导致的脆弱测试 (Flaky Tests)，
内置基于 time.monotonic() 单调时钟与轮询自旋重试状态机。
"""

from __future__ import annotations
import asyncio
import re
import time
from typing import TYPE_CHECKING, Any, overload

if TYPE_CHECKING:
    from phone_playwright.core.locator import PhoneLocator
    from phone_playwright.api.sync_api import SyncPhoneLocator


class AsyncExpect:
    """异步断言上下文管理器。"""

    def __init__(self, target: PhoneLocator, timeout_s: float = 5.0, poll_interval_s: float = 0.1) -> None:
        self._target = target
        self._timeout_s = timeout_s
        self._poll_interval_s = poll_interval_s

    async def to_be_visible(self) -> None:
        """断言目标元素在视口内可见。"""
        deadline = time.monotonic() + self._timeout_s
        while time.monotonic() < deadline:
            if await self._target.is_visible():
                return
            await asyncio.sleep(self._poll_interval_s)
        raise AssertionError(
            f"断言失败: 元素在 {self._timeout_s}s 内未能变为可见态 (selector: {self._target.selector})"
        )

    async def to_be_hidden(self) -> None:
        """断言目标元素隐藏或已从树中脱离。"""
        deadline = time.monotonic() + self._timeout_s
        while time.monotonic() < deadline:
            if not (await self._target.is_visible()):
                return
            await asyncio.sleep(self._poll_interval_s)
        raise AssertionError(
            f"断言失败: 元素在 {self._timeout_s}s 内仍处于可见态 (selector: {self._target.selector})"
        )

    async def to_have_text(self, expected: str | re.Pattern[str]) -> None:
        """断言目标元素文本完全匹配预期字符串或正则表达式。"""
        deadline = time.monotonic() + self._timeout_s
        last_text: str | None = None
        while time.monotonic() < deadline:
            last_text = await self._target.text_content()
            if last_text is not None:
                if isinstance(expected, re.Pattern):
                    if expected.search(last_text):
                        return
                elif last_text == expected:
                    return
            await asyncio.sleep(self._poll_interval_s)
        raise AssertionError(
            f"断言失败: 元素文本未能匹配期望值 (期望: {expected!r}, 实际: {last_text!r}, selector: {self._target.selector})"
        )

    async def to_contain_text(self, expected: str) -> None:
        """断言目标元素文本包含指定子串。"""
        deadline = time.monotonic() + self._timeout_s
        last_text: str | None = None
        while time.monotonic() < deadline:
            last_text = await self._target.text_content()
            if last_text is not None and expected in last_text:
                return
            await asyncio.sleep(self._poll_interval_s)
        raise AssertionError(
            f"断言失败: 元素文本未包含指定子串 (期望包含: {expected!r}, 实际: {last_text!r}, selector: {self._target.selector})"
        )

    async def to_have_count(self, expected: int) -> None:
        """断言当前视口内命中该选择器的元素总数等于 expected。"""
        deadline = time.monotonic() + self._timeout_s
        last_count = 0
        while time.monotonic() < deadline:
            last_count = await self._target.count()
            if last_count == expected:
                return
            await asyncio.sleep(self._poll_interval_s)
        raise AssertionError(
            f"断言失败: 匹配元素总数不符 (期望: {expected}, 实际: {last_count}, selector: {self._target.selector})"
        )

    async def to_be_enabled(self) -> None:
        """断言目标元素处于使能可用状态。"""
        deadline = time.monotonic() + self._timeout_s
        while time.monotonic() < deadline:
            if await self._target.is_enabled():
                return
            await asyncio.sleep(self._poll_interval_s)
        raise AssertionError(
            f"断言失败: 元素在 {self._timeout_s}s 内未能变为使能状态 (selector: {self._target.selector})"
        )

    async def to_be_disabled(self) -> None:
        """断言目标元素处于禁用置灰状态。"""
        deadline = time.monotonic() + self._timeout_s
        while time.monotonic() < deadline:
            if await self._target.is_disabled():
                return
            await asyncio.sleep(self._poll_interval_s)
        raise AssertionError(
            f"断言失败: 元素在 {self._timeout_s}s 内未能变为禁用状态 (selector: {self._target.selector})"
        )


class SyncExpect:
    """同步断言包装上下文。"""

    def __init__(self, target: SyncPhoneLocator, timeout_s: float = 5.0) -> None:
        self._target = target
        self._async_expect = AsyncExpect(
            target=target._async_page.locator(target.selector),
            timeout_s=timeout_s,
        )
        self._loop_thread = target._loop_thread

    def to_be_visible(self) -> None:
        self._loop_thread.run(self._async_expect.to_be_visible())

    def to_be_hidden(self) -> None:
        self._loop_thread.run(self._async_expect.to_be_hidden())

    def to_have_text(self, expected: str | re.Pattern[str]) -> None:
        self._loop_thread.run(self._async_expect.to_have_text(expected))

    def to_contain_text(self, expected: str) -> None:
        self._loop_thread.run(self._async_expect.to_contain_text(expected))

    def to_have_count(self, expected: int) -> None:
        self._loop_thread.run(self._async_expect.to_have_count(expected))

    def to_be_enabled(self) -> None:
        self._loop_thread.run(self._async_expect.to_be_enabled())

    def to_be_disabled(self) -> None:
        self._loop_thread.run(self._async_expect.to_be_disabled())


@overload
def expect(target: PhoneLocator, timeout_s: float = ...) -> AsyncExpect: ...

@overload
def expect(target: SyncPhoneLocator, timeout_s: float = ...) -> SyncExpect: ...

@overload
def expect(target: Any, timeout_s: float = ...) -> AsyncExpect: ...

def expect(target: Any, timeout_s: float = 5.0) -> Any:
    """构建 Playwright 风格的 expect 断言对象 (自动适配异步与同步定位器)。"""
    from phone_playwright.core.locator import PhoneLocator
    from phone_playwright.api.sync_api import SyncPhoneLocator

    if isinstance(target, PhoneLocator):
        return AsyncExpect(target=target, timeout_s=timeout_s)
    elif isinstance(target, SyncPhoneLocator):
        return SyncExpect(target=target, timeout_s=timeout_s)
    elif hasattr(target, "is_visible") and hasattr(target, "selector"):
        # 兼容鸭子类型 / 测试 Mock 对象
        return AsyncExpect(target=target, timeout_s=timeout_s)
    else:
        raise TypeError(f"expect 仅接受 PhoneLocator 或 SyncPhoneLocator，收到: {type(target)}")
