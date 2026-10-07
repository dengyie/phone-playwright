"""动作载荷与回执模式定义。"""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field
from phone_playwright.models.geometry import Rect

ActionVerb = Literal["click", "fill", "swipe", "press_key", "tap_coord", "hover", "wait_for"]


class ActionPayload(BaseModel):
    """动作下发载荷。"""

    verb: ActionVerb = Field(..., description="操作动词")
    target: str | None = Field(default=None, description="目标定位表达式，如 '@1' 或 'text=搜索'")
    value: str | None = Field(default=None, description="填充文本、按键标识或滑动方向")
    direction: Literal["up", "down", "left", "right"] | None = Field(default=None, description="滑动方向")
    duration_ms: int = Field(default=300, description="滑动或长按持续时间(ms)")
    expected_state: Literal["visible", "hidden"] = Field(default="visible", description="wait_for 断言的期望状态")
    timeout_s: float = Field(default=5.0, description="Auto-waiting 超时时间(s)")


class ActionResult(BaseModel):
    """动作执行回执。"""

    success: bool = Field(..., description="是否执行成功")
    verb: str = Field(..., description="执行的动作动词")
    target: str | None = Field(default=None, description="操作的目标")
    executed_at_bounds: Rect | None = Field(default=None, description="实际落点/操作的外接矩形")
    time_taken_ms: int = Field(..., description="耗时 (毫秒)")
    error: str | None = Field(default=None, description="错误描述")
