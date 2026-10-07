"""iOS 平台 WebDriverAgent (WDA) 驱动适配器。

通过局域网 HTTP RESTful API 直接与 iPhone 上的 WebDriverAgent 通信。
将 iOS 原生 XCTest JSON 层次树转译为统一 RawNode，无缝复用上层剪枝与状态机。
"""

from __future__ import annotations
import json
import urllib.request
import asyncio
from phone_playwright.drivers.base import BaseDriver
from phone_playwright.models.geometry import Rect
from phone_playwright.models.schema import RawNode


class IosWdaDriver(BaseDriver):
    """基于 WebDriverAgent 的 iOS 驱动实现。"""

    def __init__(self, device_id: str, wda_base_url: str = "http://localhost:8100") -> None:
        super().__init__(device_id)
        self.wda_base_url = wda_base_url.rstrip("/")
        self.session_id: str | None = None
        self._cached_viewport: tuple[int, int] | None = None

    def _http_request(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{self.wda_base_url}{path}"
        data = json.dumps(payload).encode("utf-8") if payload else None
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    async def connect(self) -> None:
        """获取 WDA 会话或探测连通性。"""
        loop = asyncio.get_running_loop()
        status = await loop.run_in_executor(None, lambda: self._http_request("GET", "/status"))
        self.session_id = status.get("sessionId")
        await self.get_viewport_size()

    async def disconnect(self) -> None:
        self.session_id = None

    async def get_viewport_size(self) -> tuple[int, int]:
        if self._cached_viewport:
            return self._cached_viewport
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, lambda: self._http_request("GET", "/window/size"))
        val = res.get("value", {})
        w = int(val.get("width", 390))
        h = int(val.get("height", 844))
        self._cached_viewport = (w, h)
        return self._cached_viewport

    async def dump_raw_tree(self) -> RawNode:
        loop = asyncio.get_running_loop()
        # WDA GET /source?format=json
        res = await loop.run_in_executor(None, lambda: self._http_request("GET", "/source?format=json"))
        raw_tree_dict = res.get("value", {})
        return parse_ios_json_hierarchy(raw_tree_dict)

    async def tap(self, x: int, y: int) -> None:
        loop = asyncio.get_running_loop()
        payload = {"x": x, "y": y}
        await loop.run_in_executor(None, lambda: self._http_request("POST", "/wda/tap/nil", payload))

    async def type_text(self, text: str) -> None:
        loop = asyncio.get_running_loop()
        payload = {"value": list(text)}
        await loop.run_in_executor(None, lambda: self._http_request("POST", "/wda/keys", payload))

    async def swipe(self, sx: int, sy: int, ex: int, ey: int, duration_ms: int = 300) -> None:
        loop = asyncio.get_running_loop()
        payload = {"fromX": sx, "fromY": sy, "toX": ex, "toY": ey, "duration": duration_ms / 1000.0}
        await loop.run_in_executor(None, lambda: self._http_request("POST", "/wda/dragfromtoforduration", payload))

    async def long_press(self, x: int, y: int, duration_ms: int = 800) -> None:
        """物理长按绝对像素坐标 (基于 WDA touchAndHold 接口)。"""
        loop = asyncio.get_running_loop()
        payload = {"x": x, "y": y, "duration": duration_ms / 1000.0}
        await loop.run_in_executor(None, lambda: self._http_request("POST", "/wda/touchAndHold", payload))

    async def press_key(self, key: str | int) -> None:
        """触发 iOS 系统或硬件按键。"""
        loop = asyncio.get_running_loop()
        k_str = str(key).lower().strip()
        if k_str in ("home", "volumeup", "volumedown"):
            await loop.run_in_executor(
                None, lambda: self._http_request("POST", "/wda/pressButton", {"name": k_str})
            )
        else:
            await loop.run_in_executor(
                None, lambda: self._http_request("POST", "/wda/keys", {"value": [str(key)]})
            )

    async def take_screenshot(self) -> bytes:
        import base64
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, lambda: self._http_request("GET", "/screenshot"))
        b64_str = res.get("value", "")
        return base64.b64decode(b64_str)

    async def get_current_app(self) -> tuple[str | None, str | None]:
        loop = asyncio.get_running_loop()
        try:
            res = await loop.run_in_executor(None, lambda: self._http_request("GET", "/wda/activeAppInfo"))
            val = res.get("value", {})
            return val.get("bundleId"), None
        except Exception:
            return None, None


def parse_ios_json_hierarchy(d: dict) -> RawNode:
    """将 iOS WDA 产出的 JSON 树递归转换为统一 RawNode。"""
    raw_rect = d.get("rect", {})
    x = int(raw_rect.get("x", 0))
    y = int(raw_rect.get("y", 0))
    w = int(raw_rect.get("width", 0))
    h = int(raw_rect.get("height", 0))
    bounds = Rect(left=x, top=y, right=x + w, bottom=y + h)

    raw_type = d.get("type", "Unknown")
    is_clickable = raw_type in ("Button", "Cell", "Link") or d.get("accessible", False)
    is_editable = "TextField" in raw_type or "SecureTextField" in raw_type

    node = RawNode(
        resource_id=d.get("name") or "",
        class_name=raw_type,
        text=d.get("label") or d.get("value") or None,
        desc=d.get("name") or None,
        bounds=bounds,
        clickable=bool(is_clickable),
        editable=bool(is_editable),
        scrollable=raw_type in ("ScrollView", "Table", "CollectionView"),
        enabled=d.get("enabled", True),
        visible=d.get("visible", True),
    )

    for child_dict in d.get("children", []):
        node.children.append(parse_ios_json_hierarchy(child_dict))

    return node
