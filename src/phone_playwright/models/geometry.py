"""几何模式与计算模块。

提供绝对像素矩形 (Rect) 与视口检测、交集计算、中心点提取等几何操作。
"""

from __future__ import annotations
from pydantic import BaseModel, Field


class Rect(BaseModel):
    """屏幕绝对物理像素矩形 [left, top, right, bottom]。"""

    left: int = Field(..., description="左上角 X 轴像素坐标")
    top: int = Field(..., description="左上角 Y 轴像素坐标")
    right: int = Field(..., description="右下角 X 轴像素坐标")
    bottom: int = Field(..., description="右下角 Y 轴像素坐标")

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def center(self) -> tuple[int, int]:
        return ((self.left + self.right) // 2, (self.top + self.bottom) // 2)

    def intersects(self, other: Rect) -> bool:
        """判定两个矩形是否有空间重叠。"""
        return not (
            self.right <= other.left
            or self.left >= other.right
            or self.bottom <= other.top
            or self.top >= other.bottom
        )

    def intersection(self, other: Rect) -> Rect | None:
        """计算两个矩形的相交区域，无重叠则返回 None。"""
        if not self.intersects(other):
            return None
        return Rect(
            left=max(self.left, other.left),
            top=max(self.top, other.top),
            right=min(self.right, other.right),
            bottom=min(self.bottom, other.bottom),
        )

    def is_visible_in_viewport(self, viewport_width: int, viewport_height: int, min_size: int = 8) -> bool:
        """判定当前矩形是否在给定视口中且具有足够的物理尺寸。"""
        vp = Rect(left=0, top=0, right=viewport_width, bottom=viewport_height)
        inter = self.intersection(vp)
        if inter is None:
            return False
        return inter.width >= min_size and inter.height >= min_size
