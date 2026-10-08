"""v2 核心模块单元测试: Set-of-Mark 渲染器与拟人化贝塞尔手势引擎。"""

import io
import math
import pytest
from PIL import Image
from phone_playwright.models.geometry import Rect
from phone_playwright.models.schema import CompactElement
from phone_playwright.core.som import SetOfMarkRenderer, _hex_to_rgb
from phone_playwright.core.gesture import (
    sigmoid_time_warp,
    generate_bezier_trajectory,
    GestureEngine,
)


def _create_dummy_png(width: int = 100, height: int = 100) -> bytes:
    img = Image.new("RGBA", (width, height), color=(255, 255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class FakeGestureDriver:
    def __init__(self) -> None:
        self.swipes: list[tuple[int, int, int, int, int]] = []
        self.long_presses: list[tuple[int, int, int]] = []

    async def get_viewport_size(self) -> tuple[int, int]:
        return 1080, 2400

    async def swipe(self, sx: int, sy: int, ex: int, ey: int, duration_ms: int = 300) -> None:
        self.swipes.append((sx, sy, ex, ey, duration_ms))

    async def long_press(self, x: int, y: int, duration_ms: int = 800) -> None:
        self.long_presses.append((x, y, duration_ms))


def test_hex_to_rgb() -> None:
    assert _hex_to_rgb("#2563EB") == (37, 99, 235)
    assert _hex_to_rgb("#FFF") == (255, 255, 255)
    assert _hex_to_rgb("invalid") == (220, 38, 38)


def test_som_renderer_basic() -> None:
    renderer = SetOfMarkRenderer()
    raw_png = _create_dummy_png(200, 400)
    elements = [
        CompactElement(
            ref="@1",
            role="button",
            text="登录",
            bounds=Rect(left=20, top=40, right=100, bottom=80),
        ),
        CompactElement(
            ref="@2",
            role="input",
            text="请输入密码",
            bounds=Rect(left=20, top=100, right=180, bottom=140),
        ),
        # 无 ref 元素不应被绘制角标
        CompactElement(
            ref=None,
            role="text",
            text="版权所有",
            bounds=Rect(left=0, top=350, right=200, bottom=380),
        ),
    ]

    som_bytes = renderer.render_som_bytes(
        image_bytes=raw_png,
        elements=elements,
        viewport_width=200,
        viewport_height=400,
    )
    assert len(som_bytes) > 0
    assert som_bytes.startswith(b"\x89PNG")

    som_b64 = renderer.render_som_base64(
        image_bytes=raw_png,
        elements=elements,
        viewport_width=200,
        viewport_height=400,
    )
    assert isinstance(som_b64, str)
    assert len(som_b64) > 100


def test_som_edge_inversion() -> None:
    renderer = SetOfMarkRenderer()
    raw_png = _create_dummy_png(100, 100)
    # 贴近屏幕顶端 (top=0) 与贴近右边界 (right=100)
    elements = [
        CompactElement(
            ref="@1",
            role="button",
            text="顶端按钮",
            bounds=Rect(left=70, top=0, right=100, bottom=20),
        )
    ]
    som_bytes = renderer.render_som_bytes(
        image_bytes=raw_png,
        elements=elements,
        viewport_width=100,
        viewport_height=100,
    )
    assert len(som_bytes) > 0


def test_sigmoid_time_warp() -> None:
    assert sigmoid_time_warp(0.0) == 0.0
    assert sigmoid_time_warp(1.0) == 1.0
    assert 0.45 < sigmoid_time_warp(0.5) < 0.55
    # 保持单调递增
    prev = -1.0
    for i in range(11):
        tau = i / 10.0
        val = sigmoid_time_warp(tau)
        assert val >= prev
        prev = val


def test_generate_bezier_trajectory() -> None:
    start = (100, 200)
    end = (500, 800)
    traj = generate_bezier_trajectory(start, end, steps=20)
    assert len(traj) == 20
    assert traj[0] == start
    assert traj[-1] == end

    # 验证同一坐标极端情况
    same_traj = generate_bezier_trajectory(start, start, steps=10)
    assert len(same_traj) == 10
    assert all(pt == start for pt in same_traj)


@pytest.mark.asyncio
async def test_gesture_engine_drag_to() -> None:
    fake_driver = FakeGestureDriver()
    engine = GestureEngine(driver=fake_driver)  # type: ignore[arg-type]

    await engine.drag_to((100, 100), (300, 500), duration_ms=400, press_duration_ms=200, steps=15)
    assert len(fake_driver.long_presses) == 1
    assert fake_driver.long_presses[0] == (100, 100, 200)
    assert len(fake_driver.swipes) > 0


@pytest.mark.asyncio
async def test_gesture_engine_swipe_path() -> None:
    fake_driver = FakeGestureDriver()
    engine = GestureEngine(driver=fake_driver)  # type: ignore[arg-type]

    points = [(100, 100), (200, 200), (300, 100)]
    await engine.swipe_path(points, duration_ms=600)
    assert len(fake_driver.swipes) == 2


@pytest.mark.asyncio
async def test_gesture_engine_pinch() -> None:
    fake_driver = FakeGestureDriver()
    engine = GestureEngine(driver=fake_driver)  # type: ignore[arg-type]

    await engine.pinch(center=(500, 1000), scale=2.0, duration_ms=300)
    assert len(fake_driver.swipes) == 2


@pytest.mark.asyncio
async def test_gesture_engine_pinch_clamps_to_viewport() -> None:
    fake_driver = FakeGestureDriver()
    engine = GestureEngine(driver=fake_driver)  # type: ignore[arg-type]

    # 测试靠近屏幕极端边缘 (10, 10) 时的安全夹紧
    await engine.pinch(center=(10, 10), scale=5.0, duration_ms=200)
    assert len(fake_driver.swipes) == 2
    for sx, sy, ex, ey, dur in fake_driver.swipes:
        assert 0 <= sx <= 1080
        assert 0 <= sy <= 2400
        assert 0 <= ex <= 1080
        assert 0 <= ey <= 2400
        assert dur > 0
