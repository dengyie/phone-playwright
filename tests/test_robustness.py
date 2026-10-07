import pytest
from phone_playwright.models.geometry import Rect
from phone_playwright.models.schema import RawNode
from phone_playwright.core.pruner import SemanticPruner
from phone_playwright.drivers.android_adb import parse_android_xml_hierarchy


def test_pruner_deeply_nested_interactive_grandchildren():
    """验证深层嵌套孙子交互元素不会被静默丢失 (Grandchildren Drop 修复验证)。"""
    pruner = SemanticPruner(min_element_size=10)

    # 构造三层结构:
    # CardView (clickable=True)
    #   └─ LinearLayout (clickable=False)
    #        ├─ TextView (文本 "热门推荐")
    #        └─ Button (clickable=True, "立即购买")
    buy_btn = RawNode(
        resource_id="com.app:id/buy_btn",
        class_name="android.widget.Button",
        text="立即购买",
        bounds=Rect(left=300, top=400, right=500, bottom=500),
        clickable=True,
    )

    card_view = RawNode(
        resource_id="com.app:id/card",
        class_name="androidx.cardview.widget.CardView",
        bounds=Rect(left=50, top=100, right=600, bottom=600),
        clickable=True,
        children=[
            RawNode(
                class_name="android.widget.LinearLayout",
                bounds=Rect(left=50, top=100, right=600, bottom=600),
                clickable=False,
                children=[
                    RawNode(
                        class_name="android.widget.TextView",
                        text="热门推荐",
                        bounds=Rect(left=60, top=120, right=200, bottom=180),
                    ),
                    buy_btn,
                ],
            )
        ],
    )

    root = RawNode(
        class_name="android.widget.FrameLayout",
        bounds=Rect(left=0, top=0, right=1080, bottom=2400),
        children=[card_view],
    )

    elements = pruner.prune_and_distill(root, viewport_width=1080, viewport_height=2400)

    # 验证卡片被识别
    card_el = next(el for el in elements if el.resource_id == "com.app:id/card")
    assert card_el.ref == "@1"
    assert "热门推荐" in card_el.text

    # 验证深层嵌套的立即购买按钮也被成功提取 (不被 Grandchildren Drop 吞噬)
    btn_el = next(el for el in elements if el.resource_id == "com.app:id/buy_btn")
    assert btn_el.ref == "@2"
    assert btn_el.text == "立即购买"


def test_multi_window_dialog_parsing():
    """验证包含并列弹窗/Dialog 的 <hierarchy> 多窗口树不会被截断。"""
    xml = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
    <hierarchy rotation="0">
      <android.widget.FrameLayout bounds="[0,0][1080,2400]">
        <android.widget.TextView text="主界面内容" bounds="[100,100][300,200]" />
      </android.widget.FrameLayout>
      <android.widget.FrameLayout bounds="[50,500][1030,1200]">
        <android.widget.Button text="允许权限" clickable="true" bounds="[200,1000][500,1150]" />
      </android.widget.FrameLayout>
    </hierarchy>
    """
    root_node = parse_android_xml_hierarchy(xml, default_width=1080, default_height=2400)
    assert len(root_node.children) == 2

    pruner = SemanticPruner()
    elements = pruner.prune_and_distill(root_node, viewport_width=1080, viewport_height=2400)

    # 两个窗口的元素均被保留
    texts = [el.text for el in elements]
    assert "主界面内容" in texts
    assert "允许权限" in texts
