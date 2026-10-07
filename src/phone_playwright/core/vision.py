"""轻量级视觉 OCR 兜底引擎 (Vision Fallback Engine)。

当无障碍树因 Canvas/游戏/自定义 View 导致失明或元素极度稀疏时触发。
采用动态可选导入 (Optional Dependency)，若环境未安装 OCR 库则安全降级。
"""

from __future__ import annotations
import io
import hashlib
from typing import Protocol, runtime_checkable
from phone_playwright.models.geometry import Rect
from phone_playwright.models.schema import CompactElement


@runtime_checkable
class VisionProvider(Protocol):
    """视觉识别提供商协议。"""

    def recognize_text_blocks(
        self, image_bytes: bytes, viewport_width: int, viewport_height: int
    ) -> list[CompactElement]:
        """从图像二进制中识别文本块并转换为 CompactElement 列表。"""
        ...


class RapidOcrFallbackProvider:
    """基于 RapidOCR / ONNX 的轻量端侧 OCR 兜底实现。"""

    def __init__(self) -> None:
        self._engine = None
        self._available = False
        self._last_image_hash: str | None = None
        self._cached_elements: list[CompactElement] = []
        self._init_engine()

    def _init_engine(self) -> None:
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-not-found]
            self._engine = RapidOCR()
            self._available = True
        except Exception:
            self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def recognize_text_blocks(
        self, image_bytes: bytes, viewport_width: int, viewport_height: int
    ) -> list[CompactElement]:
        if not self._available or not self._engine:
            return []

        # 帧图像 MD5 散列防重计算缓存
        img_hash = hashlib.md5(image_bytes).hexdigest()
        if img_hash == self._last_image_hash and self._cached_elements:
            return self._cached_elements

        try:
            results, _ = self._engine(image_bytes)
            if not results:
                return []

            elements: list[CompactElement] = []
            ref_idx = 1
            for item in results:
                # RapidOCR 输出格式: [dt_boxes, text, score]
                # dt_boxes: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                box, text, score = item[0], item[1], float(item[2])
                if score < 0.5:
                    continue

                xs = [pt[0] for pt in box]
                ys = [pt[1] for pt in box]
                x1, x2 = int(min(xs)), int(max(xs))
                y1, y2 = int(min(ys)), int(max(ys))

                rect = Rect(left=x1, top=y1, right=x2, bottom=y2)
                if not rect.is_visible_in_viewport(viewport_width, viewport_height):
                    continue

                elements.append(
                    CompactElement(
                        ref=f"@v{ref_idx}",
                        role="button" if len(text) <= 8 else "text",
                        text=text.strip(),
                        bounds=rect,
                        enabled=True,
                    )
                )
                ref_idx += 1

            self._last_image_hash = img_hash
            self._cached_elements = elements
            return elements
        except Exception:
            return []
