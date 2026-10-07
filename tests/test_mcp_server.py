"""MCP (Model Context Protocol) 核心协议与工具执行单元测试。"""

import pytest
import json
from phone_playwright.models.geometry import Rect
from phone_playwright.models.schema import RawNode
from phone_playwright.drivers.base import BaseDriver
from phone_playwright.fleet.manager import FleetManager
from phone_playwright.mcp.tools import McpToolExecutor, TOOL_DEFINITIONS
from phone_playwright.mcp.server import McpServer


class MockMcpDriver(BaseDriver):
    def __init__(self, device_id: str = "mock-phone-1") -> None:
        super().__init__(device_id)
        self.tapped: list[tuple[int, int]] = []
        self.swiped: list[tuple[int, int, int, int]] = []
        self.typed: list[str] = []
        self.keys: list[str | int] = []

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def get_viewport_size(self) -> tuple[int, int]:
        return (1080, 2400)

    async def dump_raw_tree(self) -> RawNode:
        btn = RawNode(
            class_name="android.widget.Button",
            text="立即抢购",
            bounds=Rect(left=100, top=500, right=900, bottom=600),
            clickable=True,
            enabled=True,
        )
        return RawNode(
            class_name="android.widget.FrameLayout",
            bounds=Rect(left=0, top=0, right=1080, bottom=2400),
            children=[btn],
        )

    async def tap(self, x: int, y: int) -> None:
        self.tapped.append((x, y))

    async def type_text(self, text: str) -> None:
        self.typed.append(text)

    async def swipe(self, sx: int, sy: int, ex: int, ey: int, duration_ms: int = 300) -> None:
        self.swiped.append((sx, sy, ex, ey))

    async def long_press(self, x: int, y: int, duration_ms: int = 800) -> None:
        self.tapped.append((x, y))

    async def press_key(self, key: str | int) -> None:
        self.keys.append(key)

    async def take_screenshot(self) -> bytes:
        return b"fake-png-bytes"

    async def get_current_app(self) -> tuple[str | None, str | None]:
        return "com.mock.mall", "MallActivity"


@pytest.mark.asyncio
async def test_mcp_tool_definitions():
    tool_names = [t["name"] for t in TOOL_DEFINITIONS]
    assert "phone_list_devices" in tool_names
    assert "phone_inspect_screen" in tool_names
    assert "phone_interact" in tool_names


@pytest.mark.asyncio
async def test_mcp_tool_executor_workflow(monkeypatch):
    mock_driver = MockMcpDriver("mock-phone-1")
    fleet = FleetManager()

    async def fake_scan():
        return [{"serial": "mock-phone-1", "model": "OnePlus 7T", "status": "online"}]

    async def fake_get_driver(alias_or_id: str):
        return mock_driver

    monkeypatch.setattr(fleet, "scan_devices", fake_scan)
    monkeypatch.setattr(fleet, "get_driver", fake_get_driver)

    executor = McpToolExecutor(fleet_manager=fleet)

    # 1. 测试 phone_list_devices
    devices = await executor.list_devices()
    assert len(devices) == 1
    assert devices[0]["id"] == "mock-phone-1"
    assert devices[0]["state"] == "online"

    # 2. 测试 phone_inspect_screen
    screen_info = await executor.inspect_screen("mock-phone-1", with_screenshot=True)
    assert screen_info["screen_size"] == [1080, 2400]
    assert screen_info["app_current"] == "com.mock.mall"
    assert len(screen_info["elements"]) == 1
    assert screen_info["elements"][0]["text"] == "立即抢购"
    assert "screenshot_base64" in screen_info

    # 3. 测试 phone_interact (click)
    interact_res = await executor.interact("mock-phone-1", action="click", target="@1")
    assert interact_res["status"] == "success"
    assert interact_res["action_executed"] == "click(@1)"
    assert mock_driver.tapped == [(500, 550)]

    # 4. 测试 phone_interact (press_key)
    key_res = await executor.interact("mock-phone-1", action="press_key", target="back")
    assert key_res["status"] == "success"
    assert mock_driver.keys == ["back"]

    # 5. 测试 phone_interact (swipe)
    swipe_res = await executor.interact("mock-phone-1", action="swipe", value="up")
    assert swipe_res["status"] == "success"
    assert len(mock_driver.swiped) == 1


@pytest.mark.asyncio
async def test_mcp_server_rpc_dispatch(monkeypatch):
    mock_driver = MockMcpDriver("mock-phone-1")
    fleet = FleetManager()

    async def fake_get_driver(alias_or_id: str):
        return mock_driver

    monkeypatch.setattr(fleet, "get_driver", fake_get_driver)

    server = McpServer(fleet_manager=fleet)
    sent_responses: list[dict] = []

    def mock_send(msg_id, result):
        sent_responses.append({"id": msg_id, "result": result})

    monkeypatch.setattr(server, "_send_response", mock_send)

    # 1. initialize
    await server._handle_rpc({"id": 1, "method": "initialize", "params": {}})
    assert sent_responses[-1]["result"]["serverInfo"]["name"] == "phone-playwright-mcp"

    # 2. tools/list
    await server._handle_rpc({"id": 2, "method": "tools/list", "params": {}})
    assert len(sent_responses[-1]["result"]["tools"]) == 3

    # 3. tools/call (phone_interact)
    await server._handle_rpc({
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "phone_interact",
            "arguments": {
                "device_id": "mock-phone-1",
                "action": "click",
                "target": "@1",
            },
        },
    })
    call_content = sent_responses[-1]["result"]["content"][0]["text"]
    call_data = json.loads(call_content)
    assert call_data["status"] == "success"
    assert call_data["action_executed"] == "click(@1)"


@pytest.mark.asyncio
async def test_mcp_server_run_stdio_clean_exit(monkeypatch):
    """验证 run_stdio 在接收到 stdin EOF 时平稳退出，且无 Windows IOCP 句柄崩溃。"""
    fleet = FleetManager()
    server = McpServer(fleet_manager=fleet)

    import io
    fake_stdin = io.StringIO('{"jsonrpc":"2.0","id":100,"method":"ping","params":{}}\n')
    monkeypatch.setattr("sys.stdin", fake_stdin)

    sent_responses: list[dict] = []

    def mock_send(msg_id, result):
        sent_responses.append({"id": msg_id, "result": result})

    monkeypatch.setattr(server, "_send_response", mock_send)

    await server.run_stdio()
    assert len(sent_responses) == 1
    assert sent_responses[0]["id"] == 100

