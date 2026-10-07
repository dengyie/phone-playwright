"""视口感知树剪枝与语义蒸馏器 (Viewport-Aware Semantic Pruner)。

根据当前物理视口几何尺寸，执行视口裁剪、纯布局容器剔除、语义提升合并与 @ref 索引分配。
时间复杂度: O(N) 单次深度优先遍历。
空间复杂度: O(D) 递归调用栈 (D 为树最大深度，通常 < 30)。
"""

from __future__ import annotations
from phone_playwright.models.geometry import Rect
from phone_playwright.models.schema import RawNode, CompactElement, SemanticRole


def infer_semantic_role(class_name: str, node: RawNode) -> SemanticRole:
    """基于原生类名与节点属性启发式推断无障碍语义角色。"""
    cls_lower = class_name.lower()

    if node.editable or "edittext" in cls_lower or "textfield" in cls_lower:
        return "input"
    if "button" in cls_lower or "imagebutton" in cls_lower:
        return "button"
    if "checkbox" in cls_lower:
        return "checkbox"
    if "switch" in cls_lower or "toggle" in cls_lower:
        return "switch"
    if "tab" in cls_lower:
        return "tab"
    if node.scrollable or "scrollview" in cls_lower or "recyclerview" in cls_lower or "listview" in cls_lower:
        return "scrollable"
    if node.clickable:
        if not node.text and not node.desc:
            return "item"
        return "button"
    if "imageview" in cls_lower or "image" in cls_lower:
        return "image"
    if node.text or node.desc:
        return "text"
    return "unknown"


def _collect_descendant_texts(node: RawNode, max_depth: int = 5) -> list[str]:
    """收集子树内部所有非空文本片段，用于语义提升 (Semantic Hoisting)。"""
    texts: list[str] = []

    def _dfs(n: RawNode, depth: int) -> None:
        if depth > max_depth:
            return
        t = (n.text or "").strip()
        d = (n.desc or "").strip()
        if t and t not in texts:
            texts.append(t)
        if d and d not in texts:
            texts.append(d)
        for child in n.children:
            _dfs(child, depth + 1)

    _dfs(node, 0)
    return texts


def _has_interactive_descendants(node: RawNode) -> bool:
    """递归检查当前节点下方是否存在任何可交互的子孙节点 (解决 Grandchildren Drop 缺陷)。"""
    for child in node.children:
        if child.clickable or child.editable or child.checkable:
            return True
        if _has_interactive_descendants(child):
            return True
    return False


class SemanticPruner:
    """视口感知剪枝与蒸馏器核心引擎。"""

    def __init__(self, min_element_size: int = 8) -> None:
        self.min_element_size = min_element_size

    def prune_and_distill(
        self,
        root: RawNode,
        viewport_width: int,
        viewport_height: int,
    ) -> list[CompactElement]:
        """将原始庞大节点树裁剪并转换为面向 AI 消费的紧凑元素列表。"""
        vp = Rect(left=0, top=0, right=viewport_width, bottom=viewport_height)
        result: list[CompactElement] = []
        next_ref_id = 1

        def _traverse(node: RawNode) -> None:
            nonlocal next_ref_id

            # 1. 视口几何裁剪：如果当前节点与视口完全无交集，整个子树裁剪
            inter = node.bounds.intersection(vp)
            if inter is None or inter.width < self.min_element_size or inter.height < self.min_element_size:
                return

            is_interactive = (
                node.clickable
                or node.editable
                or node.checkable
                or (node.scrollable and node.children == [])
            )

            # 2. 交互节点处理 (Interactive Element)
            if is_interactive:
                text_candidates = _collect_descendant_texts(node)
                combined_text = " ".join(text_candidates) if text_candidates else ""
                role = infer_semantic_role(node.class_name, node)

                element = CompactElement(
                    ref=f"@{next_ref_id}",
                    role=role,
                    text=combined_text,
                    bounds=node.bounds,
                    enabled=node.enabled,
                    scrollable=node.scrollable,
                    resource_id=node.resource_id or None,
                )
                result.append(element)
                next_ref_id += 1

                # 递归检查深层是否包含独立可交互孙子组件：若完全无任何交互子孙，才提前剪枝；否则继续深入遍历
                if not _has_interactive_descendants(node):
                    return

            # 3. 纯展示信息节点处理 (Static Information Display)
            elif (node.text or node.desc) and not node.children:
                raw_text = (node.text or node.desc or "").strip()
                if raw_text:
                    role = infer_semantic_role(node.class_name, node)
                    element = CompactElement(
                        ref=None,
                        role=role,
                        text=raw_text,
                        bounds=node.bounds,
                        enabled=node.enabled,
                        scrollable=False,
                        resource_id=node.resource_id or None,
                    )
                    result.append(element)
                    return

            # 4. 继续递归子树
            for child in node.children:
                _traverse(child)

        _traverse(root)
        return result
