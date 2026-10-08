"""Set-of-Mark (SoM) 视觉多模态标注渲染器。

对齐规格书: docs/specs/03-vision-som-multimodal.md
为屏幕图像中的交互元素叠加高对比度、带半透明/圆角角标的标注，
供视觉大语言模型 (VLM, 如 GPT-4o, Claude 3.5 Sonnet, Gemini 1.5 Pro) 进行无幻觉目标定位。
"""

from __future__ import annotations
import base64
import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from phone_playwright.models.schema import CompactElement

DEFAULT_SOM_PALETTE: dict[str, str] = {
    "button": "#2563EB",  # 鲜明蓝 (Vibrant Blue)
    "input": "#D97706",   # 琥珀黄 (Amber)
    "item": "#7C3AED",    # 紫色 (Purple)
    "tab": "#7C3AED",     # 紫色 (Purple)
    "text": "#4B5563",    # 板岩灰 (Slate)
    "image": "#059669",   # 翡翠绿 (Emerald Green)
    "checkbox": "#0891B2",# 青蓝 (Cyan)
    "switch": "#0891B2",  # 青蓝 (Cyan)
    "scrollable": "#64748B", # 灰蓝 (Slate Gray)
    "unknown": "#DC2626", # 红色 (Red)
}


def _hex_to_rgb(hex_code: str) -> tuple[int, int, int]:
    """十六进制颜色转 RGB 元组。"""
    h = hex_code.lstrip("#")
    if len(h) == 6:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    if len(h) == 3:
        return int(h[0] * 2, 16), int(h[1] * 2, 16), int(h[2] * 2, 16)
    return 220, 38, 38


class SetOfMarkRenderer:
    """Set-of-Mark 图像渲染器。"""

    def __init__(self, default_palette: dict[str, str] | None = None) -> None:
        self.palette = dict(DEFAULT_SOM_PALETTE)
        if default_palette:
            self.palette.update(default_palette)

    def render_som_bytes(
        self,
        image_bytes: bytes,
        elements: list[CompactElement],
        viewport_width: int,
        viewport_height: int,
        palette_override: dict[str, str] | None = None,
    ) -> bytes:
        """在给定的屏幕截图上渲染 SoM 角标与外框，返回 PNG 图像二进制字节。"""
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            # 环境无 Pillow 时降级返回原始字节
            return image_bytes

        if not image_bytes or not elements:
            return image_bytes

        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        except Exception:
            return image_bytes

        img_w, img_h = image.size
        if viewport_width <= 0 or viewport_height <= 0:
            scale_x, scale_y = 1.0, 1.0
        else:
            scale_x = float(img_w) / float(viewport_width)
            scale_y = float(img_h) / float(viewport_height)

        active_palette = dict(self.palette)
        if palette_override:
            active_palette.update(palette_override)

        # 筛选具备 ref 标识的元素，并按元素面积降序排列绘制 (大容器先画，小叶子后画在顶层)
        interactive_elements = [el for el in elements if el.ref]
        interactive_elements.sort(
            key=lambda e: (e.bounds.right - e.bounds.left) * (e.bounds.bottom - e.bounds.top),
            reverse=True,
        )

        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        for el in interactive_elements:
            ref = el.ref or ""
            role = el.role
            hex_color = active_palette.get(role, active_palette.get("unknown", "#DC2626"))
            rgb = _hex_to_rgb(hex_color)
            stroke_color = (rgb[0], rgb[1], rgb[2], 255)
            badge_bg_color = (rgb[0], rgb[1], rgb[2], 230)
            text_color = (255, 255, 255, 255)

            # 仿射变换计算位图绝对像素边界
            x1 = max(0, min(img_w, int(round(el.bounds.left * scale_x))))
            y1 = max(0, min(img_h, int(round(el.bounds.top * scale_y))))
            x2 = max(0, min(img_w, int(round(el.bounds.right * scale_x))))
            y2 = max(0, min(img_h, int(round(el.bounds.bottom * scale_y))))

            if x2 <= x1 or y2 <= y1:
                continue

            # 1. 绘制 2px 细边框外接矩形
            draw.rectangle([x1, y1, x2, y2], outline=stroke_color, width=2)

            # 2. 准备角标标签文本，形如 [@1]
            label_text = f"[{ref}]" if not ref.startswith("[") else ref

            # 3. 测量文本宽度与高度
            if font is not None and hasattr(draw, "textbbox"):
                bbox = draw.textbbox((0, 0), label_text, font=font)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
            elif font is not None and hasattr(font, "getsize"):
                tw, th = font.getsize(label_text)
            else:
                tw = len(label_text) * 7
                th = 12

            pad_x = 4
            pad_y = 2
            bw = tw + pad_x * 2
            bh = th + pad_y * 2

            # 4. 角标避让与防遮挡定位 (Edge Inversion)
            # 默认锚点: 元素左上方外侧
            bx = x1
            by = y1 - bh

            # 顶端越界检查: 贴近顶端时倒贴至元素内部左上角
            if by < 0:
                by = y1

            # 右边缘越界检查: 贴近右边缘时向左对齐
            if bx + bw > img_w:
                bx = max(0, int(x2 - bw))

            # 绘制圆角背景 Badge
            if hasattr(draw, "rounded_rectangle"):
                draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=3, fill=badge_bg_color)
            else:
                draw.rectangle([bx, by, bx + bw, by + bh], fill=badge_bg_color)

            # 绘制居中文本
            text_x = bx + pad_x
            text_y = by + pad_y
            if font:
                draw.text((text_x, text_y), label_text, font=font, fill=text_color)
            else:
                draw.text((text_x, text_y), label_text, fill=text_color)

        output_buf = io.BytesIO()
        image.save(output_buf, format="PNG")
        return output_buf.getvalue()

    def render_som_base64(
        self,
        image_bytes: bytes,
        elements: list[CompactElement],
        viewport_width: int,
        viewport_height: int,
        palette_override: dict[str, str] | None = None,
    ) -> str:
        """渲染并返回 Base64 编码的 PNG 字符串。"""
        out_bytes = self.render_som_bytes(
            image_bytes=image_bytes,
            elements=elements,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            palette_override=palette_override,
        )
        return base64.b64encode(out_bytes).decode("ascii")
