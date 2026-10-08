"""拟人化手势与三阶贝塞尔曲线平滑轨迹引擎 (Advanced Gesture Engine)。

对齐规格书: docs/specs/04-gesture-engine.md
包含:
1. 三阶贝塞尔曲线插值 (Cubic Bézier Interpolation)
2. 法向量正交高斯扰动 (Gaussian Perturbation)
3. Sigmoid 非线性时钟扭曲 (Sigmoid Time-Warping Function)
4. 多点手势分发器 (拖拽 drag_to, 缩放 pinch, 连续折线 swipe_path)
"""

from __future__ import annotations
import asyncio
import math
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from phone_playwright.drivers.base import BaseDriver


def sigmoid_time_warp(tau: float, k: float = 10.0) -> float:
    """Sigmoid 变加速时间扭曲函数，生成拟人化的'启动加速 -> 高速滑动 -> 减速释放'物理时钟。

    tau in [0.0, 1.0], 返回归一化后单调递增的 t in [0.0, 1.0]。
    """
    if tau <= 0.0:
        return 0.0
    if tau >= 1.0:
        return 1.0

    # s(tau) = 1 / (1 + exp(-k * (tau - 0.5)))
    # 归一化: (s(tau) - s(0)) / (s(1) - s(0))
    s_0 = 1.0 / (1.0 + math.exp(0.5 * k))
    s_1 = 1.0 / (1.0 + math.exp(-0.5 * k))
    s_tau = 1.0 / (1.0 + math.exp(-k * (tau - 0.5)))
    val = (s_tau - s_0) / (s_1 - s_0)
    return max(0.0, min(1.0, val))


def generate_bezier_trajectory(
    start: tuple[int, int],
    end: tuple[int, int],
    steps: int = 25,
    k: float = 10.0,
    deviation_scale: float = 0.08,
) -> list[tuple[int, int]]:
    """生成符合人类生物力学的三阶贝塞尔平滑滑动轨迹点阵序列。

    参数:
        start: 起点像素坐标 (x0, y0)
        end: 终点像素坐标 (x3, y3)
        steps: 插值采样步数 (默认 25 步)
        k: Sigmoid 时间扭曲曲率 (默认 10.0)
        deviation_scale: 控制点正交扰动标准差比例 (默认 0.08 * 距离)
    """
    if steps < 2:
        return [start, end]

    x0, y0 = float(start[0]), float(start[1])
    x3, y3 = float(end[0]), float(end[1])
    dx = x3 - x0
    dy = y3 - y0
    dist = math.hypot(dx, dy)

    if dist < 1e-4:
        return [start] * steps

    # 计算法向量正交单位向量 n = (-dy / dist, dx / dist)
    nx = -dy / dist
    ny = dx / dist

    sigma = deviation_scale * dist
    delta1 = random.gauss(0.0, sigma)
    delta2 = random.gauss(0.0, sigma)

    # 计算控制点 P1 与 P2
    p1_x = x0 + dx / 3.0 + nx * delta1
    p1_y = y0 + dy / 3.0 + ny * delta1

    p2_x = x0 + 2.0 * dx / 3.0 + nx * delta2
    p2_y = y0 + 2.0 * dy / 3.0 + ny * delta2

    trajectory: list[tuple[int, int]] = []
    for i in range(steps):
        tau = float(i) / float(steps - 1)
        t = sigmoid_time_warp(tau, k=k)

        # 三阶贝塞尔公式: B(t) = (1-t)^3*P0 + 3(1-t)^2*t*P1 + 3(1-t)*t^2*P2 + t^3*P3
        c0 = (1.0 - t) ** 3
        c1 = 3.0 * ((1.0 - t) ** 2) * t
        c2 = 3.0 * (1.0 - t) * (t ** 2)
        c3 = t ** 3

        bx = c0 * x0 + c1 * p1_x + c2 * p2_x + c3 * x3
        by = c0 * y0 + c1 * p1_y + c2 * p2_y + c3 * y3

        trajectory.append((int(round(bx)), int(round(by))))

    # 边界约束: 首尾严格重合
    trajectory[0] = start
    trajectory[-1] = end
    return trajectory


class GestureEngine:
    """高级手势分发引擎。"""

    def __init__(self, driver: BaseDriver) -> None:
        self.driver = driver

    async def drag_to(
        self,
        source_point: tuple[int, int],
        target_point: tuple[int, int],
        duration_ms: int = 600,
        press_duration_ms: int = 300,
        steps: int = 25,
    ) -> None:
        """从起点按压准备后，沿平滑轨迹拖拽至终点。

        针对具备原生 drag_and_drop 的驱动 (如 AndroidAdbDriver)，执行单手势原子拖拽，避免分段抬手；
        针对通用驱动，保持按压准备与平滑轨迹下发。
        """
        if hasattr(self.driver, "drag_and_drop") and callable(getattr(self.driver, "drag_and_drop")):
            await self.driver.drag_and_drop(
                source_point[0], source_point[1], target_point[0], target_point[1], duration_ms=duration_ms + press_duration_ms
            )
            await asyncio.sleep(0.05)
            return

        # 1. 起点长按准备态
        if press_duration_ms > 0:
            await self.driver.long_press(source_point[0], source_point[1], duration_ms=press_duration_ms)
            await asyncio.sleep(0.05)

        # 2. 生成拟人贝塞尔点阵
        traj = generate_bezier_trajectory(source_point, target_point, steps=steps)

        # 3. 针对通用驱动执行高效分段滑动
        # 为平衡平滑度与跨进程 ADB 通信开销，抽取 6~8 个代表性折线关键帧依次下发
        sample_count = min(len(traj), max(4, steps // 3))
        indices = [int(round(i * (len(traj) - 1) / (sample_count - 1))) for i in range(sample_count)]
        sampled_points = [traj[idx] for idx in indices]

        segment_duration = max(30, duration_ms // max(1, len(sampled_points) - 1))
        for i in range(len(sampled_points) - 1):
            p_start = sampled_points[i]
            p_end = sampled_points[i + 1]
            await self.driver.swipe(
                p_start[0], p_start[1], p_end[0], p_end[1], duration_ms=segment_duration
            )

        await asyncio.sleep(0.05)

    async def swipe_path(
        self,
        points: list[tuple[int, int]],
        duration_ms: int = 800,
    ) -> None:
        """沿多点折线连续滑动 (如九宫格锁屏、连续滑块)。"""
        if len(points) < 2:
            return

        total_dist = sum(
            math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1])
            for i in range(len(points) - 1)
        )
        if total_dist <= 0:
            return

        for i in range(len(points) - 1):
            p_start = points[i]
            p_end = points[i + 1]
            seg_dist = math.hypot(p_end[0] - p_start[0], p_end[1] - p_start[1])
            seg_duration = max(30, int(duration_ms * (seg_dist / total_dist)))
            await self.driver.swipe(
                p_start[0], p_start[1], p_end[0], p_end[1], duration_ms=seg_duration
            )

    async def pinch(
        self,
        center: tuple[int, int],
        scale: float,
        duration_ms: int = 400,
    ) -> None:
        """执行双指捏合或张开缩放动作。

        scale > 1.0 为张开 (放大 / pinch out)
        scale < 1.0 为捏合 (缩小 / pinch in)
        """
        cx, cy = center
        vw, vh = await self.driver.get_viewport_size()
        base_radius = min(vw, vh) * 0.25

        if scale >= 1.0:
            # 放大: 从内向外
            r_start = base_radius * 0.5
            r_end = min(min(vw, vh) * 0.45, base_radius * scale)
        else:
            # 缩小: 从外向内
            r_start = min(min(vw, vh) * 0.45, base_radius / max(0.1, scale))
            r_end = base_radius * 0.5

        # 边界约束: 限制双指坐标必须在物理安全视口以内 (防触摸出界抛错)
        p1_start = (max(10, min(vw - 10, int(cx - r_start))), max(10, min(vh - 10, cy)))
        p1_end = (max(10, min(vw - 10, int(cx - r_end))), max(10, min(vh - 10, cy)))
        p2_start = (max(10, min(vw - 10, int(cx + r_start))), max(10, min(vh - 10, cy)))
        p2_end = (max(10, min(vw - 10, int(cx + r_end))), max(10, min(vh - 10, cy)))

        # 依次快速分发两侧轨迹
        half_dur = max(50, duration_ms // 2)
        await self.driver.swipe(p1_start[0], p1_start[1], p1_end[0], p1_end[1], duration_ms=half_dur)
        await self.driver.swipe(p2_start[0], p2_start[1], p2_end[0], p2_end[1], duration_ms=half_dur)
