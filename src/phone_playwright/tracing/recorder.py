"""Playwright 兼容 Trace Viewer 录制引擎 (Trace Recorder)。

对齐规格书: docs/specs/06-expect-assertions-and-trace.md
包含:
1. 流式捕获动作前后快照 (Snapshots & Screenshots)
2. 动作时序指标与 JSONL 事件流 (trace.trace)
3. 静态资源 SHA-256 哈希池 (resources/)
4. 打包导出为标准的 Playwright 兼容 trace.zip
"""

from __future__ import annotations
import asyncio
import hashlib
import io
import json
import os
import time
import zipfile
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from phone_playwright.drivers.base import BaseDriver
    from phone_playwright.models.schema import PageSnapshot


class TraceRecorder:
    """自动化测试 Trace 录制管理器。"""

    def __init__(self, driver: BaseDriver) -> None:
        self.driver = driver
        self.is_recording = False
        self.record_screenshots = True
        self.record_snapshots = True
        self.start_time: float = 0.0
        self.events: list[dict[str, Any]] = []
        self.resources: dict[str, bytes] = {}  # sha256 -> content
        self._lock = asyncio.Lock()

    async def start(self, screenshots: bool = True, snapshots: bool = True) -> None:
        """开启 Trace 录制。"""
        async with self._lock:
            self.is_recording = True
            self.record_screenshots = screenshots
            self.record_snapshots = snapshots
            self.start_time = time.time()
            self.events.clear()
            self.resources.clear()

    def _store_resource(self, data: bytes, ext: str = "bin") -> str:
        """存储资源并返回相对路径 resources/{sha256}.{ext}。"""
        sha = hashlib.sha256(data).hexdigest()
        filename = f"{sha}.{ext}"
        rel_path = f"resources/{filename}"
        if sha not in self.resources:
            self.resources[sha] = data
        return rel_path

    async def record_action(
        self,
        name: str,
        selector: str | None = None,
        duration_ms: int = 0,
        click_point: tuple[int, int] | None = None,
        snapshot_before: PageSnapshot | None = None,
        snapshot_after: PageSnapshot | None = None,
        screenshot_bytes: bytes | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """记录单个动作事件。"""
        if not self.is_recording:
            return

        async with self._lock:
            event: dict[str, Any] = {
                "type": "action",
                "name": name,
                "timestamp": time.time(),
                "duration_ms": duration_ms,
                "selector": selector,
            }
            if click_point:
                event["click_point"] = {"x": click_point[0], "y": click_point[1]}

            if error:
                event["error"] = error

            if screenshot_bytes and self.record_screenshots:
                event["screenshot"] = self._store_resource(screenshot_bytes, ext="png")

            if snapshot_before and self.record_snapshots:
                tree_bytes = snapshot_before.to_markdown().encode("utf-8")
                event["snapshot_before"] = self._store_resource(tree_bytes, ext="md")

            if snapshot_after and self.record_snapshots:
                tree_bytes = snapshot_after.to_markdown().encode("utf-8")
                event["snapshot_after"] = self._store_resource(tree_bytes, ext="md")

            if metadata:
                event["metadata"] = metadata

            self.events.append(event)

    async def stop(self, path: str = "trace.zip") -> str:
        """停止录制并将所有时序事件、前后快照及元数据打包导出为 Playwright 兼容的 trace.zip。"""
        async with self._lock:
            self.is_recording = False
            end_time = time.time()

            # 1. 构建 manifest.json
            vw, vh = 0, 0
            try:
                vw, vh = await self.driver.get_viewport_size()
            except Exception:
                pass

            manifest = {
                "schemaVersion": 1,
                "created": {
                    "time": self.start_time,
                    "duration": int((end_time - self.start_time) * 1000),
                },
                "device": {
                    "device_id": self.driver.device_id,
                    "viewport": {"width": vw, "height": vh},
                },
                "eventCount": len(self.events),
            }

            # 2. 生成 trace.trace (JSONL 格式)
            trace_lines = [json.dumps(evt, ensure_ascii=False) for evt in self.events]
            trace_content = "\n".join(trace_lines).encode("utf-8")

            # 3. 写入 Zip 文件
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
                zf.writestr("trace.trace", trace_content)

                # 写入资源池
                for sha, content in self.resources.items():
                    # 推断扩展名
                    ext = "bin"
                    if content.startswith(b"\x89PNG"):
                        ext = "png"
                    elif content.startswith(b"\xff\xd8"):
                        ext = "jpg"
                    elif content.startswith(b"# Device Viewport"):
                        ext = "md"
                    zf.writestr(f"resources/{sha}.{ext}", content)

            return os.path.abspath(path)


class SyncTraceRecorder:
    """同步模式下的 Trace 录制代理。"""

    def __init__(self, async_recorder: TraceRecorder, loop_thread: Any) -> None:
        self._async = async_recorder
        self._loop_thread = loop_thread

    def start(self, screenshots: bool = True, snapshots: bool = True) -> None:
        self._loop_thread.run(self._async.start(screenshots=screenshots, snapshots=snapshots))

    def stop(self, path: str = "trace.zip") -> str:
        return str(self._loop_thread.run(self._async.stop(path=path)))
