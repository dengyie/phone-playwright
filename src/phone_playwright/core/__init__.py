"""核心领域包导出。"""

from phone_playwright.core.pruner import SemanticPruner, infer_semantic_role
from phone_playwright.core.selector import Selector, parse_selector
from phone_playwright.core.state_machine import ActionabilityEngine
from phone_playwright.core.locator import PhoneLocator
from phone_playwright.core.vision import RapidOcrFallbackProvider

__all__ = [
    "SemanticPruner",
    "infer_semantic_role",
    "Selector",
    "parse_selector",
    "ActionabilityEngine",
    "PhoneLocator",
    "RapidOcrFallbackProvider",
]
