import pytest
from phone_playwright.models.geometry import Rect


def test_rect_basic_properties():
    r = Rect(left=100, top=200, right=500, bottom=600)
    assert r.width == 400
    assert r.height == 400
    assert r.area == 160000
    assert r.center == (300, 400)


def test_rect_intersection_and_viewport():
    r1 = Rect(left=0, top=0, right=100, bottom=100)
    r2 = Rect(left=50, top=50, right=150, bottom=150)
    inter = r1.intersection(r2)
    assert inter is not None
    assert inter.left == 50
    assert inter.top == 50
    assert inter.right == 100
    assert inter.bottom == 100

    # 视口外元素
    r_offscreen = Rect(left=0, top=2500, right=1080, bottom=2700)
    assert not r_offscreen.is_visible_in_viewport(1080, 2400)

    # 视口内有效元素
    r_onscreen = Rect(left=50, top=100, right=500, bottom=200)
    assert r_onscreen.is_visible_in_viewport(1080, 2400)
