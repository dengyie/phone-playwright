"""选择器特异性解析单元测试 (Selector specificity)。

覆盖 get_by_text 因祖先容器聚合子节点文本而贪婪命中全屏根节点的缺陷：
必须优先精确文本匹配，其次取面积最小 (最叶子/最具体) 的命中元素。
"""

from phone_playwright.core.selector import parse_selector
from phone_playwright.models.geometry import Rect
from phone_playwright.models.schema import CompactElement


def _el(ref, text, left, top, right, bottom, role="item"):
    return CompactElement(
        ref=ref,
        role=role,
        text=text,
        bounds=Rect(left=left, top=top, right=right, bottom=bottom),
    )


def test_text_selector_prefers_exact_match_over_substring_container():
    # 根 scrollable 全屏且聚合了子节点文本；button 为精确匹配的图标
    root = _el("@1", "数字时钟 应用宝 图库 文件管理", 0, 0, 1280, 720, role="scrollable")
    item = _el("@2", "数字时钟 应用宝 图库 文件管理", 0, 0, 1280, 720)
    button = _el("@4", "应用宝", 172, 307, 328, 419, role="button")
    selector = parse_selector("text=应用宝")

    picked = selector.find_first([root, item, button])

    assert picked is button


def test_text_selector_prefers_smallest_area_when_no_exact_match():
    big = _el("@1", "包含搜索关键字的超长聚合文本", 0, 0, 1280, 720)
    small = _el("@2", "包含搜索关键字", 100, 100, 300, 160)
    selector = parse_selector("text=搜索关键字")

    picked = selector.find_first([big, small])

    assert picked is small


def test_exact_text_selector_requires_equality():
    container = _el("@1", "前缀 目标文本 后缀", 0, 0, 1280, 720)
    exact = _el("@2", "目标文本", 10, 10, 110, 50)
    selector = parse_selector("exact:text=目标文本")

    picked = selector.find_first([container, exact])

    assert picked is exact
    # 仅子串含的容器不应被 exact 选择器命中
    assert selector.find_first([container]) is None


def test_ref_selector_keeps_declaration_order():
    a = _el("@1", "甲", 0, 0, 100, 100)
    b = _el("@2", "甲", 200, 200, 300, 300)
    selector = parse_selector("@1")

    picked = selector.find_first([a, b])

    assert picked is a


def test_id_selector_ignores_text_specificity():
    a = _el("@1", "长文本聚合", 0, 0, 1280, 720)
    b = _el("@2", "长文本聚合", 5, 5, 20, 20)
    a.resource_id = "com.app:id/target"
    b.resource_id = "com.app:id/target"
    selector = parse_selector("id=com.app:id/target")

    picked = selector.find_first([a, b])

    assert picked is a  # 保持原始顺序，不按面积重排


def test_chained_selector_with_nth_filtering():
    """验证链式选择器 (Chained Locators) 与 nth 过滤。"""
    btn0 = _el("@1", "添加到购物车", 0, 0, 100, 50, role="button")
    btn1 = _el("@2", "添加到购物车", 0, 60, 100, 110, role="button")
    btn2 = _el("@3", "立即购买", 0, 120, 100, 170, role="button")
    elements = [btn0, btn1, btn2]

    # 1. 链式 role >> text
    sel_buy = parse_selector("role=button >> text=立即购买")
    assert sel_buy.find_first(elements) is btn2

    # 2. 链式 role >> nth=1
    sel_nth1 = parse_selector("role=button >> nth=1")
    assert sel_nth1.find_first(elements) is btn1

    # 3. 链式 role >> text=添加到购物车 >> nth=0
    sel_cart_first = parse_selector("role=button >> text=添加到购物车 >> nth=0")
    assert sel_cart_first.find_first(elements) is btn0

    # 4. 越界保护
    sel_overflow = parse_selector("role=button >> nth=99")
    assert sel_overflow.find_first(elements) is None