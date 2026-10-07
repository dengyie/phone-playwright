"""同步 SDK API 门面 (Sync API)。

通过专用后台线程事件循环封装底层 asyncio 内核，
提供与 Playwright Python 同步模式完全一致的简洁阻塞式体验。
"""

from __future__ import annotations
import asyncio
import threading
from typing import Any, Coroutine, TypeVar, Literal
from phone_playwright.api.async_api import (
    AsyncPhonePlaywright,
    AsyncPhoneDevice,
    AsyncPhonePage,
)
from phone_playwright.models.schema import PageSnapshot
from phone_playwright.models.actions import ActionResult

T = TypeVar("T")


class SyncEventLoopThread:
    """专用后台事件循环工作线程。"""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=2.0)


class SyncPhoneLocator:
    """同步定位器包装。"""

    def __init__(self, async_page: AsyncPhonePage, selector: str, loop_thread: SyncEventLoopThread) -> None:
        self._async_page = async_page
        self._selector = selector
        self._loop_thread = loop_thread

    @property
    def selector(self) -> str:
        """对外暴露定位器表达式，与 AsyncPhoneLocator 保持契约一致。"""
        return self._selector

    def click(self, timeout_s: float = 5.0) -> ActionResult:
        coro = self._async_page.locator(self._selector).click(timeout_s=timeout_s)
        return self._loop_thread.run(coro)

    def fill(self, text: str, timeout_s: float = 5.0) -> ActionResult:
        coro = self._async_page.locator(self._selector).fill(text=text, timeout_s=timeout_s)
        return self._loop_thread.run(coro)

    def hover(self, timeout_s: float = 5.0, duration_ms: int = 800) -> ActionResult:
        coro = self._async_page.locator(self._selector).hover(timeout_s=timeout_s, duration_ms=duration_ms)
        return self._loop_thread.run(coro)

    def wait_for(
        self, state: Literal["visible", "hidden"] = "visible", timeout_s: float = 5.0
    ) -> ActionResult:
        coro = self._async_page.locator(self._selector).wait_for(state=state, timeout_s=timeout_s)
        return self._loop_thread.run(coro)

    def scroll_into_view(
        self,
        max_swipes: int = 5,
        direction: Literal["up", "down"] = "up",
        distance_ratio: float = 0.5,
    ) -> SyncPhoneLocator:
        coro = self._async_page.locator(self._selector).scroll_into_view(
            max_swipes=max_swipes,
            direction=direction,
            distance_ratio=distance_ratio,
        )
        self._loop_thread.run(coro)
        return self

    def is_visible(self) -> bool:
        coro = self._async_page.locator(self._selector).is_visible()
        return self._loop_thread.run(coro)

    def count(self) -> int:
        coro = self._async_page.locator(self._selector).count()
        return self._loop_thread.run(coro)

    def text_content(self) -> str | None:
        coro = self._async_page.locator(self._selector).text_content()
        return self._loop_thread.run(coro)

    def bounding_box(self) -> dict[str, int] | None:
        coro = self._async_page.locator(self._selector).bounding_box()
        return self._loop_thread.run(coro)


class SyncPhonePage:
    """同步页面操作实例。"""

    def __init__(self, async_page: AsyncPhonePage, loop_thread: SyncEventLoopThread) -> None:
        self._async = async_page
        self._loop_thread = loop_thread

    def __call__(self) -> SyncPhonePage:
        """支持 device.current_page() 函数式调用习惯。"""
        return self

    def snapshot(
        self,
        use_vision_fallback: bool = False,
        include_screenshot: bool = False,
    ) -> PageSnapshot:
        return self._loop_thread.run(
            self._async.snapshot(
                use_vision_fallback=use_vision_fallback,
                include_screenshot=include_screenshot,
            )
        )

    def screenshot(self) -> bytes:
        return self._loop_thread.run(self._async.screenshot())

    def locator(self, selector: str) -> SyncPhoneLocator:
        return SyncPhoneLocator(
            async_page=self._async,
            selector=selector,
            loop_thread=self._loop_thread,
        )

    def get_by_text(self, text: str, exact: bool = False) -> SyncPhoneLocator:
        prefix = "exact:text=" if exact else "text="
        return self.locator(f"{prefix}{text}")

    def get_by_role(self, role: str, name: str | None = None) -> SyncPhoneLocator:
        sel = f"role={role}[name={name}]" if name else f"role={role}"
        return self.locator(sel)

    def dump_raw_tree(self) -> Any:
        return self._loop_thread.run(self._async.dump_raw_tree())

    def swipe(self, *args: Any, **kwargs: Any) -> None:
        self._loop_thread.run(self._async.swipe(*args, **kwargs))

    def press_key(self, key: str | int) -> None:
        self._loop_thread.run(self._async.press_key(key))

    def press_back(self) -> None:
        self._loop_thread.run(self._async.press_back())

    def press_home(self) -> None:
        self._loop_thread.run(self._async.press_home())


class SyncPhoneDevice:
    """同步设备实例。"""

    def __init__(self, async_device: AsyncPhoneDevice, loop_thread: SyncEventLoopThread) -> None:
        self._async = async_device
        self._loop_thread = loop_thread
        self._page = SyncPhonePage(async_page=async_device.current_page, loop_thread=loop_thread)

    @property
    def current_page(self) -> SyncPhonePage:
        return self._page

    @property
    def page(self) -> SyncPhonePage:
        return self._page

    def locator(self, selector: str) -> SyncPhoneLocator:
        return self._page.locator(selector)

    def get_by_text(self, text: str, exact: bool = False) -> SyncPhoneLocator:
        return self._page.get_by_text(text, exact=exact)

    def get_by_role(self, role: str, name: str | None = None) -> SyncPhoneLocator:
        return self._page.get_by_role(role, name=name)

    def get_by_test_id(self, test_id: str) -> SyncPhoneLocator:
        return self._page.get_by_test_id(test_id)

    def snapshot(
        self,
        use_vision_fallback: bool = False,
        include_screenshot: bool = False,
    ) -> PageSnapshot:
        return self._page.snapshot(
            use_vision_fallback=use_vision_fallback,
            include_screenshot=include_screenshot,
        )

    def dump_raw_tree(self) -> Any:
        return self._page.dump_raw_tree()

    def swipe(self, *args: Any, **kwargs: Any) -> None:
        self._page.swipe(*args, **kwargs)

    def press_back(self) -> None:
        self._page.press_back()

    def press_home(self) -> None:
        self._page.press_home()


class SyncPhonePlaywright:
    """同步上下文管理器顶层入口。"""

    def __init__(self, adb_path: str = "adb") -> None:
        self._loop_thread = SyncEventLoopThread()
        self._async_playwright = AsyncPhonePlaywright(adb_path=adb_path)

    def __enter__(self) -> SyncPhonePlaywright:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    def connect(self, alias_or_id: str = "", device_id: str = "") -> SyncPhoneDevice:
        target = device_id or alias_or_id
        async_dev = self._loop_thread.run(self._async_playwright.connect(target))
        return SyncPhoneDevice(async_device=async_dev, loop_thread=self._loop_thread)

    def list_devices(self) -> list[dict[str, str]]:
        return self._loop_thread.run(self._async_playwright.list_devices())

    def close(self) -> None:
        try:
            self._loop_thread.run(self._async_playwright.fleet.close_all())
        finally:
            self._loop_thread.stop()


def sync_phone_playwright(adb_path: str = "adb") -> SyncPhonePlaywright:
    """同步上下文管理器入口工厂。"""
    return SyncPhonePlaywright(adb_path=adb_path)
