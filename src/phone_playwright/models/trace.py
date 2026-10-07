"""Playwright 兼容 Trace 领域数据模型。"""

from __future__ import annotations
from typing import Literal, Any
from pydantic import BaseModel, Field
from phone_playwright.models.geometry import Rect


class TraceActionRecord(BaseModel):
    """单步动作时序追踪记录。"""

    type: Literal["action"] = "action"
    name: str = Field(..., description="动作名称, 如 click, fill, swipe")
    timestamp: float = Field(..., description="事件触发时间戳 (Unix 秒)")
    duration_ms: int = Field(..., description="执行总耗时 (毫秒)")
    selector: str | None = Field(default=None, description="目标选择器")
    matched_bounds: Rect | None = Field(default=None, description="匹配到的元素物理边界")
    click_point: tuple[int, int] | None = Field(default=None, description="实际点击坐标 (x, y)")
    text_input: str | None = Field(default=None, description="输入的文本内容 (针对 fill/type)")
    snapshot_before_ref: str | None = Field(default=None, description="动作前快照在资源包中的相对路径")
    snapshot_after_ref: str | None = Field(default=None, description="动作后快照在资源包中的相对路径")
    success: bool = Field(default=True, description="动作是否成功")
    error: str | None = Field(default=None, description="错误描述")
    metadata: dict[str, Any] = Field(default_factory=dict, description="额外调试元数据")


class TraceManifest(BaseModel):
    """Trace 包元信息清单 (manifest.json)。"""

    version: str = "2.0"
    framework: str = "phone-playwright"
    device_id: str
    platform: str = "android"
    viewport_width: int
    viewport_height: int
    start_time: float
    end_time: float | None = None
    actions_count: int = 0
