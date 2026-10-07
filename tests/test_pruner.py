import pytest
from phone_playwright.models.geometry import Rect
from phone_playwright.models.schema import RawNode
from phone_playwright.core.pruner import SemanticPruner


def test_pruner_semantic_hoisting_and_clipping():
    # 模拟一个真实的 Android 深度嵌套列表项:
    # FrameLayout (视口外) -> 必须被剪枝
    # LinearLayout (视口内, 可点击卡片) 内部包含两个只读 TextView -> 必须被提升合并为单个 @ref 元素
    pruner = SemanticPruner(min_element_size=10)

    # 视口外节点
    offscreen_child = RawNode(
        class_name="android.widget.TextView",
        text="视口外文字",
        bounds=Rect(left=0, top=2500, right=1080, bottom=2600),
        clickable=True,
    )

    # 视口内可点击卡片
    card_container = RawNode(
        resource_id="com.taobao:id/item_card",
        class_name="android.widget.LinearLayout",
        bounds=Rect(left=50, top=200, right=500, bottom=600),
        clickable=True,
        children=[
            RawNode(
                class_name="android.widget.TextView",
                text="一加 7T 手机",
                bounds=Rect(left=60, top=210, right=400, bottom=260),
            ),
            RawNode(
                class_name="android.widget.TextView",
                text="￥699",
                bounds=Rect(left=60, top=270, right=200, bottom=310),
            ),
        ],
    )

    # 搜索框
    search_input = RawNode(
        resource_id="com.taobao:id/search_box",
        class_name="android.widget.EditText",
        text="请输入搜索词",
        bounds=Rect(left=100, top=50, right=900, bottom=150),
        clickable=True,
        editable=True,
    )

    root = RawNode(
        class_name="android.widget.FrameLayout",
        bounds=Rect(left=0, top=0, right=1080, bottom=2400),
        children=[search_input, card_container, offscreen_child],
    )

    elements = pruner.prune_and_distill(root, viewport_width=1080, viewport_height=2400)

    # 断言 1: 视口外节点被剪枝
    assert not any(el.text == "视口外文字" for el in elements)

    # 断言 2: 搜索框被正确识别为 input
    input_el = next(el for el in elements if el.role == "input")
    assert input_el.ref == "@1"
    assert input_el.text == "请输入搜索词"

    # 断言 3: 可点击卡片内的子文本被提升合并
    card_el = next(el for el in elements if el.resource_id == "com.taobao:id/item_card")
    assert card_el.ref == "@2"
    assert "一加 7T 手机" in card_el.text
    assert "￥699" in card_el.text
