"""选择器解析器 (Selector Engine)。

支持丰富的定位策略:
- @ref: '@1', '@4' (最优先，O(1) 精准命中)
- text: 'text=搜索', 'text="加入购物车"' (支持完全匹配与子串匹配)
- role: 'role=button[name=确定]'
- id: 'id=com.app:id/submit_btn'
"""

from __future__ import annotations
import re
from typing import Callable
from phone_playwright.models.schema import CompactElement


class Selector:
    """已解析的选择器对象。"""

    def __init__(self, raw: str, matcher: Callable[[CompactElement], bool]) -> None:
        self.raw = raw
        self.matcher = matcher

    def match(self, element: CompactElement) -> bool:
        return self.matcher(element)

    def find_first(self, elements: list[CompactElement]) -> CompactElement | None:
        """从紧凑元素列表中查找首个满足匹配的元素。"""
        for el in elements:
            if self.match(el):
                return el
        return None

    def __str__(self) -> str:
        return self.raw


def parse_selector(selector_str: str) -> Selector:
    """将选择器字符串解析为可执行匹配器。"""
    s = selector_str.strip()

    # 1. 匹配 @ref: '@1', '@12'
    if s.startswith("@"):
        target_ref = s
        return Selector(
            raw=s,
            matcher=lambda el: el.ref == target_ref,
        )

    # 2. 匹配 id=xxx 或 resource-id=xxx
    if s.startswith("id=") or s.startswith("resource-id="):
        target_id = s.split("=", 1)[1].strip().strip('"').strip("'")
        return Selector(
            raw=s,
            matcher=lambda el: el.resource_id == target_id,
        )

    # 3. 匹配 text=xxx 或 exact:text=xxx
    if s.startswith("exact:text="):
        target_text = s.split("=", 1)[1].strip().strip('"').strip("'")
        return Selector(
            raw=s,
            matcher=lambda el: el.text == target_text,
        )

    if s.startswith("text="):
        target_text = s.split("=", 1)[1].strip().strip('"').strip("'")
        return Selector(
            raw=s,
            matcher=lambda el: target_text in el.text,
        )

    # 4. 匹配 role=xxx[name=yyy] 或 role=xxx
    role_pattern = re.compile(r"^role=([a-zA-Z]+)(?:\[name=([^\]]+)\])?$")
    role_match = role_pattern.match(s)
    if role_match:
        role_name = role_match.group(1).lower()
        name_val = role_match.group(2)
        if name_val:
            name_val = name_val.strip().strip('"').strip("'")
            return Selector(
                raw=s,
                matcher=lambda el: el.role == role_name and (name_val in el.text),
            )
        return Selector(
            raw=s,
            matcher=lambda el: el.role == role_name,
        )

    # 5. 默认行为：宽松子串文本匹配
    fallback_text = s.strip('"').strip("'")
    return Selector(
        raw=s,
        matcher=lambda el: fallback_text in el.text,
    )
