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

    def __init__(
        self,
        raw: str,
        matcher: Callable[[CompactElement], bool],
        exact_text: str | None = None,
        substring_text: str | None = None,
    ) -> None:
        self.raw = raw
        self.matcher = matcher
        self.exact_text = exact_text
        self.substring_text = substring_text

    def match(self, element: CompactElement) -> bool:
        return self.matcher(element)

    def find_first(self, elements: list[CompactElement]) -> CompactElement | None:
        """返回最具体的首个匹配。

        文本类选择器常因祖先容器聚合了子节点文本而形成"子串含"匹配
        (如全屏根 scrollable 的文本包含"应用宝")，若按列表顺序取首个会命中
        全屏容器，导致点击/取边界落在屏幕中心而非目标图标。此处按特异性评分：
        1. exact_text 选择器：精确等值文本优先于子串命中；
        2. substring_text 选择器：命中集合中取面积最小 (最叶子/最具体) 者；
        3. @ref / id / role 等无文本偏向的选择器保持原始列表顺序。
        """
        best: CompactElement | None = None
        best_score: float = float("inf")
        for el in elements:
            if not self.match(el):
                continue
            if self.exact_text is not None:
                score = 0.0 if el.text == self.exact_text else 1.0
            elif self.substring_text is not None:
                area = (el.bounds.right - el.bounds.left) * (el.bounds.bottom - el.bounds.top)
                score = 1.0 + float(area)
            else:
                score = 2.0
            if score < best_score:
                best, best_score = el, score
        return best

    def find_all(self, elements: list[CompactElement]) -> list[CompactElement]:
        """返回所有匹配的元素集合。"""
        return [el for el in elements if self.match(el)]

    def __str__(self) -> str:
        return self.raw


def parse_selector(selector_str: str) -> Selector:
    """将选择器字符串解析为可执行匹配器，全面支持复合管道链式选择器 (>>) 与 nth 索引。"""
    s = selector_str.strip()

    # 处理链式复合选择器: "role=list >> text=商品" 或 "role=button >> nth=1"
    if " >> " in s:
        parts = [p.strip() for p in s.split(" >> ") if p.strip()]
        if len(parts) > 1:
            selectors = [parse_selector(p) for p in parts]

            def chained_match(el: CompactElement) -> bool:
                # 对于复合选择器，最末级子选择器必须匹配
                return selectors[-1].match(el)

            chained_sel = Selector(raw=s, matcher=chained_match)

            def chained_find_first(elements: list[CompactElement]) -> CompactElement | None:
                current_pool = list(elements)
                for sub_sel in selectors:
                    # 检查是否为 nth 伪类选择器
                    if sub_sel.raw.startswith("nth="):
                        try:
                            idx = int(sub_sel.raw.split("=", 1)[1].strip())
                            if 0 <= idx < len(current_pool):
                                current_pool = [current_pool[idx]]
                            elif idx < 0 and abs(idx) <= len(current_pool):
                                current_pool = [current_pool[idx]]
                            else:
                                return None
                        except ValueError:
                            return None
                    else:
                        matched = sub_sel.find_all(current_pool)
                        if not matched:
                            return None
                        current_pool = matched
                return current_pool[0] if current_pool else None

            def chained_find_all(elements: list[CompactElement]) -> list[CompactElement]:
                current_pool = list(elements)
                for sub_sel in selectors:
                    if sub_sel.raw.startswith("nth="):
                        try:
                            idx = int(sub_sel.raw.split("=", 1)[1].strip())
                            if 0 <= idx < len(current_pool):
                                current_pool = [current_pool[idx]]
                            elif idx < 0 and abs(idx) <= len(current_pool):
                                current_pool = [current_pool[idx]]
                            else:
                                return []
                        except ValueError:
                            return []
                    else:
                        current_pool = sub_sel.find_all(current_pool)
                return current_pool

            chained_sel.find_first = chained_find_first  # type: ignore[assignment]
            chained_sel.find_all = chained_find_all      # type: ignore[assignment]
            return chained_sel

    # 1. 匹配 nth=xxx
    if s.startswith("nth="):
        return Selector(raw=s, matcher=lambda el: True)

    # 2. 匹配 @ref: '@1', '@12'
    if s.startswith("@"):
        target_ref = s
        return Selector(
            raw=s,
            matcher=lambda el: el.ref == target_ref,
        )

    # 3. 匹配 id=xxx 或 resource-id=xxx
    if s.startswith("id=") or s.startswith("resource-id="):
        target_id = s.split("=", 1)[1].strip().strip('"').strip("'")
        return Selector(
            raw=s,
            matcher=lambda el: el.resource_id == target_id,
        )

    # 4. 匹配 text=xxx 或 exact:text=xxx
    if s.startswith("exact:text="):
        target_text = s.split("=", 1)[1].strip().strip('"').strip("'")
        return Selector(
            raw=s,
            matcher=lambda el: el.text == target_text,
            exact_text=target_text,
        )

    if s.startswith("text="):
        target_text = s.split("=", 1)[1].strip().strip('"').strip("'")
        return Selector(
            raw=s,
            matcher=lambda el: target_text in el.text,
            substring_text=target_text,
        )

    # 5. 匹配 role=xxx[name=yyy] 或 role=xxx
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

    # 6. 默认行为：宽松子串文本匹配
    fallback_text = s.strip('"').strip("'")
    return Selector(
        raw=s,
        matcher=lambda el: fallback_text in el.text,
        substring_text=fallback_text,
    )
