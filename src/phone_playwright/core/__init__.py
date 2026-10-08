"""核心领域包导出。"""

from phone_playwright.core.pruner import SemanticPruner, infer_semantic_role
from phone_playwright.core.selector import Selector, parse_selector
from phone_playwright.core.state_machine import ActionabilityEngine
from phone_playwright.core.locator import PhoneLocator
from phone_playwright.core.vision import RapidOcrFallbackProvider
from phone_playwright.core.som import SetOfMarkRenderer, DEFAULT_SOM_PALETTE
from phone_playwright.core.gesture import (
    GestureEngine,
    generate_bezier_trajectory,
    sigmoid_time_warp,
)
from phone_playwright.core.cdp import (
    CdpClient,
    CdpDiscovery,
    WebFrameLocator,
    WebPhoneLocator,
)

from phone_playwright.core.assertions import (
    AsyncExpect,
    SyncExpect,
    expect,
)

__all__ = [
    "SemanticPruner",
    "infer_semantic_role",
    "Selector",
    "parse_selector",
    "ActionabilityEngine",
    "PhoneLocator",
    "RapidOcrFallbackProvider",
    "SetOfMarkRenderer",
    "DEFAULT_SOM_PALETTE",
    "GestureEngine",
    "generate_bezier_trajectory",
    "sigmoid_time_warp",
    "CdpClient",
    "CdpDiscovery",
    "WebFrameLocator",
    "WebPhoneLocator",
    "AsyncExpect",
    "SyncExpect",
    "expect",
]
