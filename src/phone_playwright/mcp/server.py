"""标准 MCP (Model Context Protocol) STDIO 服务端实现。

遵循 JSON-RPC 2.0 规范，提供即插即用的 STDIO 通信管道，
使 ZCode / Claude Code / Cursor 等宿主模型能够直接发现与调用 Phone-Playwright。
"""

from __future__ import annotations
import asyncio
import json
import sys
from typing import Any, Dict
from phone_playwright.mcp.tools import TOOL_DEFINITIONS, McpToolExecutor
from phone_playwright.fleet.manager import FleetManager


class McpServer:
    """MCP STDIO JSON-RPC 2.0 服务端。"""

    def __init__(self, fleet_manager: FleetManager | None = None) -> None:
        self.fleet = fleet_manager or FleetManager()
        self.executor = McpToolExecutor(fleet_manager=self.fleet)

    async def run_stdio(self) -> None:
        """从标准输入监听 JSON-RPC 2.0 请求并向标准输出响应。"""
        loop = asyncio.get_running_loop()

        while True:
            line_str = await loop.run_in_executor(None, sys.stdin.readline)
            if not line_str:
                break

            line_str = line_str.strip()
            if not line_str:
                continue

            try:
                request = json.loads(line_str)
            except Exception as e:
                self._send_error(None, -32700, f"Parse error: {e}")
                continue

            await self._handle_rpc(request)

    async def _handle_rpc(self, request: dict[str, Any]) -> None:
        msg_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        if method == "initialize":
            self._send_response(msg_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                },
                "serverInfo": {
                    "name": "phone-playwright-mcp",
                    "version": "0.1.0",
                },
            })
            return

        if method == "notifications/initialized":
            # 客户端就绪确认通知，无需回复 id
            return

        if method == "ping":
            self._send_response(msg_id, {})
            return

        if method == "tools/list":
            self._send_response(msg_id, {
                "tools": TOOL_DEFINITIONS,
            })
            return

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            try:
                result_data: Any = None
                if tool_name == "phone_list_devices":
                    result_data = await self.executor.list_devices()
                elif tool_name == "phone_inspect_screen":
                    device_id = arguments["device_id"]
                    with_shot = arguments.get("with_screenshot", False)
                    use_vision = arguments.get("use_vision_fallback", False)
                    result_data = await self.executor.inspect_screen(
                        device_id=device_id,
                        with_screenshot=with_shot,
                        use_vision_fallback=use_vision,
                    )
                elif tool_name == "phone_interact":
                    device_id = arguments["device_id"]
                    action = arguments["action"]
                    target = arguments.get("target")
                    value = arguments.get("value")
                    timeout_s = float(arguments.get("timeout_s", 5.0))
                    result_data = await self.executor.interact(
                        device_id=device_id,
                        action=action,
                        target=target,
                        value=value,
                        timeout_s=timeout_s,
                    )
                else:
                    self._send_error(msg_id, -32601, f"Unknown tool: {tool_name}")
                    return

                self._send_response(msg_id, {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result_data, ensure_ascii=False, indent=2),
                        }
                    ],
                })
            except Exception as e:
                self._send_response(msg_id, {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Error executing tool {tool_name}: {e}",
                        }
                    ],
                    "isError": True,
                })
            return

        self._send_error(msg_id, -32601, f"Method not found: {method}")

    def _send_response(self, msg_id: Any, result: Any) -> None:
        if msg_id is None:
            return
        payload = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": result,
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def _send_error(self, msg_id: Any, code: int, message: str) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": code,
                "message": message,
            },
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()


PhonePlaywrightMcpServer = McpServer


def main() -> None:
    """MCP STDIO 服务入口点。"""
    server = McpServer()
    asyncio.run(server.run_stdio())


if __name__ == "__main__":
    main()
