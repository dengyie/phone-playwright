"""领域数据模式定义。

包含多叉原始树节点 (RawNode)、紧凑语义元素 (CompactElement)、页面快照 (PageSnapshot)。
"""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field
from phone_playwright.models.geometry import Rect

SemanticRole = Literal[
    "button",
    "input",
    "item",
    "text",
    "image",
    "tab",
    "checkbox",
    "switch",
    "scrollable",
    "unknown",
]


class RawNode(BaseModel):
    """跨平台统一多叉原始节点，封装 Android XML 与 iOS JSON 树。"""

    resource_id: str = Field(default="", description="原生资源 ID，如 com.app:id/btn")
    class_name: str = Field(default="", description="原生组件类名")
    text: str | None = Field(default=None, description="控件直接显示的文字")
    desc: str | None = Field(default=None, description="无障碍描述 (contentDescription)")
    bounds: Rect = Field(..., description="绝对像素边界")
    clickable: bool = Field(default=False, description="是否可点击")
    editable: bool = Field(default=False, description="是否可编辑输入")
    scrollable: bool = Field(default=False, description="是否可滚动")
    checkable: bool = Field(default=False, description="是否可勾选切换")
    enabled: bool = Field(default=True, description="是否处于使能状态")
    visible: bool = Field(default=True, description="原生可见性标记")
    children: list[RawNode] = Field(default_factory=list, description="多叉子节点列表")


class CompactElement(BaseModel):
    """剪枝蒸馏后提供给 AI 消费的紧凑语义元素。"""

    ref: str | None = Field(
        default=None,
        description="唯一交互标识符，形如 '@1'。仅交互元素拥有，纯展示元素为 None",
    )
    role: SemanticRole = Field(..., description="推断出的语义角色")
    text: str = Field(default="", description="聚合/提升后的文本或无障碍描述")
    bounds: Rect = Field(..., description="物理绝对像素边界")
    enabled: bool = Field(default=True, description="是否使能")
    scrollable: bool = Field(default=False, description="是否可滚动")
    resource_id: str | None = Field(default=None, description="原生资源 ID (辅助调试)")


class PageSnapshot(BaseModel):
    """当前活跃屏幕的视口语义快照。"""

    timestamp: float = Field(..., description="快照时间戳 (Unix 秒)")
    device_id: str = Field(..., description="设备标识")
    package_name: str | None = Field(default=None, description="当前前台包名/应用名")
    activity_name: str | None = Field(default=None, description="当前前台 Activity")
    viewport_width: int = Field(..., description="物理视口宽度")
    viewport_height: int = Field(..., description="物理视口高度")
    elements: list[CompactElement] = Field(default_factory=list, description="视口内紧凑元素列表")
    screenshot_base64: str | None = Field(default=None, description="物理屏幕截图 Base64 数据 (可选)")

    def to_markdown(self) -> str:
        """为 LLM 生成最高信息密度、最少 Token 的 Markdown 清单。"""
        lines = [f"# Device Viewport: {self.viewport_width}x{self.viewport_height}"]
        if self.package_name:
            lines.append(f"# Active App: {self.package_name}")
        lines.append("## Interactive Elements:")
        for el in self.elements:
            clean_text = el.text.replace("\n", " ").strip()
            if el.ref:
                lines.append(f"- [{el.ref}] {el.role}: \"{clean_text}\"")
            else:
                lines.append(f"- (info) {el.role}: \"{clean_text}\"")
        return "\n".join(lines)

    @property
    def summary_markdown(self) -> str:
        return self.to_markdown()
