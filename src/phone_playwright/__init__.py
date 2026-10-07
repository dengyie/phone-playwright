"""Phone-Playwright 顶层包入口。

暴露最符合直觉的工厂方法:
from phone_playwright import sync_phone_playwright, async_phone_playwright
"""

from phone_playwright.api.sync_api import (
    sync_phone_playwright,
    SyncPhonePlaywright,
    SyncPhoneDevice,
    SyncPhonePage,
    SyncPhoneLocator,
)
from phone_playwright.api.async_api import (
    async_phone_playwright,
    AsyncPhonePlaywright,
    AsyncPhoneDevice,
    AsyncPhonePage,
)
from phone_playwright.core.locator import PhoneLocator
from phone_playwright.models.geometry import Rect
from phone_playwright.models.schema import CompactElement, PageSnapshot
from phone_playwright.models.actions import ActionResult
from phone_playwright.models.exceptions import (
    PhonePlaywrightError,
    DeviceOfflineError,
    ActionabilityTimeoutError,
    SelectorNotFoundError,
    OffscreenElementError,
)

__all__ = [
    "sync_phone_playwright",
    "async_phone_playwright",
    "SyncPhonePlaywright",
    "SyncPhoneDevice",
    "SyncPhonePage",
    "SyncPhoneLocator",
    "PhoneLocator",
    "AsyncPhonePlaywright",
    "AsyncPhoneDevice",
    "AsyncPhonePage",
    "Rect",
    "CompactElement",
    "PageSnapshot",
    "ActionResult",
    "PhonePlaywrightError",
    "DeviceOfflineError",
    "ActionabilityTimeoutError",
    "SelectorNotFoundError",
    "OffscreenElementError",
]
