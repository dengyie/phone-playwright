"""MCP (Model Context Protocol) 核心工具定义与执行器。

严格对齐 docs/API_SPEC.md 规范:
- phone_list_devices: 扫描并列出局域网与 USB 可用移动设备
- phone_inspect_screen: 拉取指定设备的屏幕视口紧凑树与多模态感知数据
- phone_interact: 执行具备 Auto-waiting 状态机的 Playwright 动作
"""

from __future__ import annotations
import base64
import json
from typing import Any, Dict, List, Literal
from phone_playwright.fleet.manager import FleetManager
from phone_playwright.api.async_api import AsyncPhoneDevice
from phone_playwright.models.actions import ActionResult

TOOL_DEFINITIONS = [
    {
        "name": "phone_list_devices",
        "description": "扫描局域网 (Wi-Fi ADB) 与 USB，列出当前所有在线可用的移动物理设备。",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "phone_inspect_screen",
        "description": "拉取指定设备的当前屏幕视口紧凑语义树与前台活跃应用，作为 AI 的视觉神经系统。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "目标设备序列号或局域网 IP:Port (如 '192.168.1.3:43037')",
                },
                "with_screenshot": {
                    "type": "boolean",
                    "description": "是否附带物理屏幕截图的 Base64 编码",
                    "default": False,
                },
                "use_vision_fallback": {
                    "type": "boolean",
                    "description": "当无障碍树节点稀疏或遇纯渲染页面时，是否激活本地 OCR 兜底识别",
                    "default": False,
                },
            },
            "required": ["device_id"],
        },
    },
    {
        "name": "phone_interact",
        "description": "对手机下发语义化交互动作，内置 Playwright 风格的 Auto-waiting 状态机 (Attached -> Visible -> Stable -> Enabled)。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "目标设备序列号或局域网地址",
                },
                "action": {
                    "type": "string",
                    "enum": ["click", "fill", "hover", "swipe", "press_key", "wait_for"],
                    "description": "执行动作类型",
                },
                "target": {
                    "type": "string",
                    "description": "目标元素的 @ref 编号 (如 '@1') 或语义选择器 (如 'text=搜索')",
                },
                "value": {
                    "type": "string",
                    "description": "动作参数: 填充文本 (fill)、滑动方向 'up'/'down' (swipe) 或按键名称 'back'/'home' (press_key)",
                },
                "timeout_s": {
                    "type": "number",
                    "description": "Auto-waiting 超时等待时间(秒)",
                    "default": 5.0,
                },
            },
            "required": ["device_id", "action"],
        },
    },
]


class McpToolExecutor:
    """MCP 工具调用异步执行器。"""

    def __init__(self, fleet_manager: FleetManager | None = None) -> None:
        self.fleet = fleet_manager or FleetManager()

    async def list_devices(self) -> list[dict[str, Any]]:
        raw_devices = await self.fleet.scan_devices()
        return [
            {
                "id": d["serial"],
                "model": d["model"],
                "platform": "android",
                "state": d["status"],
            }
            for d in raw_devices
        ]

    async def inspect_screen(
        self,
        device_id: str,
        with_screenshot: bool = False,
        use_vision_fallback: bool = False,
    ) -> dict[str, Any]:
        driver = await self.fleet.get_driver(device_id)
        device = AsyncPhoneDevice(driver=driver)
        page = device.current_page
        snapshot = await page.snapshot(use_vision_fallback=use_vision_fallback)

        element_items: list[dict[str, Any]] = []
        for el in snapshot.elements:
            item: dict[str, Any] = {
                "role": el.role,
                "text": el.text,
                "bounds": [el.bounds.left, el.bounds.top, el.bounds.right, el.bounds.bottom],
            }
            if el.ref:
                item["ref"] = el.ref
            element_items.append(item)

        result: dict[str, Any] = {
            "device": device_id,
            "screen_size": [snapshot.viewport_width, snapshot.viewport_height],
            "app_current": snapshot.package_name,
            "activity_current": snapshot.activity_name,
            "element_count": len(snapshot.elements),
            "elements": element_items,
            "markdown_tree": snapshot.to_markdown(),
        }

        if with_screenshot:
            img_bytes = await page.screenshot()
            result["screenshot_base64"] = base64.b64encode(img_bytes).decode("ascii")

        return result

    async def interact(
        self,
        device_id: str,
        action: str,
        target: str | None = None,
        value: str | None = None,
        timeout_s: float = 5.0,
    ) -> dict[str, Any]:
        driver = await self.fleet.get_driver(device_id)
        device = AsyncPhoneDevice(driver=driver)
        page = device.current_page

        if action == "swipe":
            direction = (value or "up").lower()
            if direction not in ("up", "down", "left", "right"):
                direction = "up"
            await page.swipe(direction=direction)  # type: ignore[arg-type]
            return {
                "status": "success",
                "action_executed": f"swipe({direction})",
                "waited_ms": 0,
            }

        if action == "press_key":
            key_name = value or target or "back"
            await page.press_key(key_name)
            return {
                "status": "success",
                "action_executed": f"press_key({key_name})",
                "waited_ms": 0,
            }

        if not target:
            raise ValueError(f"动作 '{action}' 必须提供 target 参数 (如 '@1' 或 'text=搜索')")

        locator = page.locator(target)

        if action == "click":
            res = await locator.click(timeout_s=timeout_s)
        elif action == "fill":
            res = await locator.fill(text=value or "", timeout_s=timeout_s)
        elif action == "hover":
            res = await locator.hover(timeout_s=timeout_s)
        elif action == "wait_for":
            expected: Literal["visible", "hidden"] = (
                "hidden" if (value or "").lower() == "hidden" else "visible"
            )
            res = await locator.wait_for(state=expected, timeout_s=timeout_s)
        else:
            raise ValueError(f"不支持的操作类型: {action}")

        target_bounds = (
            [
                res.executed_at_bounds.left,
                res.executed_at_bounds.top,
                res.executed_at_bounds.right,
                res.executed_at_bounds.bottom,
            ]
            if res.executed_at_bounds
            else None
        )

        return {
            "status": "success" if res.success else "failed",
            "action_executed": f"{res.verb}({res.target})",
            "target_bounds": target_bounds,
            "waited_ms": res.time_taken_ms,
            "error": res.error,
        }
