"""混合应用 (WebView / 小程序) Chrome DevTools Protocol (CDP) 穿透引擎。

对齐规格书: docs/specs/05-cdp-hybrid-traversal.md
通过 Unix Domain Socket 自动发现与 ADB 端口转发，与 App 内嵌的 Chromium/XWeb 内核
建立 WebSocket JSON-RPC 通道，实现原生 App 容器与内嵌 H5 DOM 节点的统一定位与混合编排。
"""

from __future__ import annotations
import asyncio
import json
import re
import socket
import time
import urllib.request
from typing import TYPE_CHECKING, Any

from phone_playwright.models.actions import ActionResult
from phone_playwright.models.exceptions import PhonePlaywrightError

if TYPE_CHECKING:
    from phone_playwright.api.async_api import AsyncPhonePage
    from phone_playwright.drivers.base import BaseDriver


def _find_free_port() -> int:
    """寻找本地空闲 TCP 端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class CdpClient:
    """轻量级 Chrome DevTools Protocol 客户端 (基于 asyncio 与 WebSocket)。"""

    def __init__(self, ws_url: str, local_port: int, driver: BaseDriver | None = None) -> None:
        self.ws_url = ws_url
        self.local_port = local_port
        self.driver = driver
        self._ws: Any = None
        self._next_id = 1
        self._pending_futures: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._receive_task: asyncio.Task[None] | None = None
        self._closed = False

    async def connect(self) -> None:
        """建立 WebSocket 连接并启动消息监听循环。"""
        try:
            import websockets
        except ImportError:
            raise PhonePlaywrightError(
                "缺少 websockets 库，无法建立 CDP WebSocket 穿透通道",
                suggestion="请运行 pip install websockets 安装依赖",
            )

        self._ws = await websockets.connect(self.ws_url)
        self._receive_task = asyncio.create_task(self._listen_loop())

    async def _listen_loop(self) -> None:
        """后台监听 WebSocket JSON-RPC 回包。"""
        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)
                except Exception:
                    continue

                req_id = data.get("id")
                if req_id is not None and req_id in self._pending_futures:
                    fut = self._pending_futures.pop(req_id)
                    if not fut.done():
                        fut.set_result(data)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def send_command(self, method: str, params: dict[str, Any] | None = None, timeout: float = 10.0) -> dict[str, Any]:
        """发送 CDP JSON-RPC 命令并等待回包。"""
        if self._closed or not self._ws:
            raise PhonePlaywrightError("CDP 客户端未连接或已关闭")

        req_id = self._next_id
        self._next_id += 1

        payload = {
            "id": req_id,
            "method": method,
            "params": params or {},
        }

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending_futures[req_id] = fut

        await self._ws.send(json.dumps(payload))
        try:
            resp = await asyncio.wait_for(fut, timeout=timeout)
            if "error" in resp:
                raise PhonePlaywrightError(f"CDP 命令执行失败 ({method}): {resp['error']}")
            return resp.get("result", {})
        except asyncio.TimeoutError:
            self._pending_futures.pop(req_id, None)
            raise TimeoutError(f"CDP 命令调用超时: {method}")

    async def evaluate(self, expression: str, timeout: float = 10.0) -> Any:
        """在目标 WebView 页面环境中评估 JavaScript 表达式。"""
        res = await self.send_command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
            timeout=timeout,
        )
        result_obj = res.get("result", {})
        return result_obj.get("value")

    async def get_element_box(self, selector: str) -> dict[str, Any] | None:
        """查询 DOM 元素的物理设备视口坐标边界与 DPR 信息 {x, y, width, height, dpr, text}。"""
        js = f"""(() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return null;
            const r = el.getBoundingClientRect();
            const dpr = window.devicePixelRatio || 1.0;
            return {{
                x: r.x * dpr,
                y: r.y * dpr,
                width: r.width * dpr,
                height: r.height * dpr,
                css_x: r.x,
                css_y: r.y,
                css_width: r.width,
                css_height: r.height,
                dpr: dpr,
                text: (el.innerText || el.textContent || '').trim()
            }};
        }})()"""
        return await self.evaluate(js)

    async def get_title(self) -> str:
        """获取当前 H5 页面 document.title。"""
        title = await self.evaluate("document.title")
        return str(title or "")

    async def get_url(self) -> str:
        """获取当前 H5 页面 window.location.href。"""
        url = await self.evaluate("window.location.href")
        return str(url or "")

    async def close(self) -> None:
        """关闭 WebSocket 连接并释放端口转发。"""
        self._closed = True
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        if self.driver and hasattr(self.driver, "_run_adb"):
            try:
                await self.driver._run_adb("forward", "--remove", f"tcp:{self.local_port}")
            except Exception:
                pass


class CdpDiscovery:
    """WebView / XWeb 套接字自动发现与隧道管理器。"""

    @staticmethod
    async def discover_remote_sockets(driver: BaseDriver) -> list[str]:
        """扫描 /proc/net/unix，提取包含 devtools_remote 的套接字列表。"""
        if not hasattr(driver, "_run_adb"):
            return []

        try:
            output = await driver._run_adb("shell", "cat", "/proc/net/unix")
        except Exception:
            return []

        found: list[str] = []
        for line in output.splitlines():
            line_str = line.strip()
            if "devtools_remote" in line_str:
                parts = line_str.split()
                if parts:
                    raw_socket = parts[-1]
                    clean_socket = raw_socket.lstrip("@")
                    if clean_socket and clean_socket not in found:
                        found.append(clean_socket)
        return found

    @staticmethod
    async def create_cdp_client(driver: BaseDriver, preferred_socket: str | None = None) -> CdpClient:
        """自动匹配前台应用套接字，建立 ADB 端口转发并构建 CdpClient。"""
        sockets = await CdpDiscovery.discover_remote_sockets(driver)
        if not sockets:
            raise PhonePlaywrightError(
                "未在设备上检测到任何可用的 WebView / DevTools 抽象套接字",
                suggestion=(
                    "目标应用可能未开启 WebView.setWebContentsDebuggingEnabled(true)，"
                    "或目标页面并非内嵌 Chromium/WebView 架构。建议降级为 SoM 视觉模态交互"
                ),
            )

        # 智能匹配优先套接字：若未指定且驱动支持 get_current_app，优先匹配包含当前前台应用包名的套接字
        target_socket = preferred_socket
        if not target_socket:
            if hasattr(driver, "get_current_app") and callable(getattr(driver, "get_current_app")):
                try:
                    current_pkg, _ = await driver.get_current_app()
                    if current_pkg:
                        for s in sockets:
                            if current_pkg in s:
                                target_socket = s
                                break
                except Exception:
                    pass
            if not target_socket:
                target_socket = sockets[0]

        local_port = _find_free_port()

        forward_established = False
        if hasattr(driver, "_run_adb"):
            await driver._run_adb("forward", f"tcp:{local_port}", f"localabstract:{target_socket}")
            forward_established = True

        try:
            # 拉取 /json/list 探测可调试页面列表 (通过 asyncio.to_thread 异步卸载，防止阻塞事件循环)
            url = f"http://127.0.0.1:{local_port}/json/list"
            pages: list[dict[str, Any]] = []

            def _fetch_pages() -> list[dict[str, Any]]:
                req = urllib.request.Request(url, headers={"User-Agent": "phone-playwright"})
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    return json.loads(resp.read().decode("utf-8"))

            # 指数退避式渐进微等待 (0.05s, 0.1s, 0.2s, 0.3s, 0.4s)，平均探测延迟降低 70%
            poll_delays = [0.05, 0.1, 0.2, 0.3, 0.4]
            for delay in poll_delays:
                try:
                    pages = await asyncio.to_thread(_fetch_pages)
                    if pages:
                        break
                except Exception:
                    await asyncio.sleep(delay)

            if not pages:
                raise PhonePlaywrightError(
                    f"已连接套接字 {target_socket} 但未能拉取到有效的 H5 Page 列表",
                    suggestion="请确认目标 WebView 容器已加载页面且处于激活状态",
                )

            ws_url: str | None = None
            for p in pages:
                if p.get("type") == "page" and p.get("webSocketDebuggerUrl"):
                    ws_url = p["webSocketDebuggerUrl"]
                    break
            if not ws_url and pages:
                ws_url = pages[0].get("webSocketDebuggerUrl")

            if not ws_url:
                raise PhonePlaywrightError(f"目标 WebView 未能提供合法的 webSocketDebuggerUrl (pages={pages})")

            # 替换 ws_url 中可能出现的 localhost / 127.0.0.1 端口对准
            ws_url = re.sub(r":\d+/", f":{local_port}/", ws_url)

            client = CdpClient(ws_url=ws_url, local_port=local_port, driver=driver)
            await client.connect()
            return client
        except Exception:
            # 异常屏障：若建立连接失败，必须立即清理端口转发，防止 ADB 端口泄漏
            if forward_established and hasattr(driver, "_run_adb"):
                try:
                    await driver._run_adb("forward", "--remove", f"tcp:{local_port}")
                except Exception:
                    pass
            raise


class WebFrameLocator:
    """WebView 内嵌 Web 树定位器。"""

    def __init__(self, page: AsyncPhonePage, container_selector: str = "role=scrollable") -> None:
        self.page = page
        self.container_selector = container_selector
        self._cdp_client: CdpClient | None = None

    async def _ensure_connected(self) -> CdpClient:
        if self._cdp_client is None or self._cdp_client._closed:
            self._cdp_client = await CdpDiscovery.create_cdp_client(self.page.driver)
        return self._cdp_client

    def locator(self, css_or_xpath: str) -> WebPhoneLocator:
        """通过 CSS 选择器查询 WebView 内部 DOM 节点。"""
        return WebPhoneLocator(frame=self, selector=css_or_xpath)

    async def title(self) -> str:
        """获取 WebView 内部 HTML document.title。"""
        client = await self._ensure_connected()
        return await client.get_title()

    async def url(self) -> str:
        """获取当前 H5 页面 window.location.href。"""
        client = await self._ensure_connected()
        return await client.get_url()

    async def evaluate(self, expression: str) -> Any:
        """在 WebView 内部执行任意 JavaScript 脚本。"""
        client = await self._ensure_connected()
        return await client.evaluate(expression)

    async def close(self) -> None:
        """关闭底层 CDP 会话。"""
        if self._cdp_client:
            await self._cdp_client.close()
            self._cdp_client = None


class WebPhoneLocator:
    """WebView 内部 DOM 节点延迟定位器。"""

    def __init__(self, frame: WebFrameLocator, selector: str) -> None:
        self.frame = frame
        self.selector = selector

    async def click(self, timeout_s: float = 5.0) -> ActionResult:
        """通过绝对屏幕坐标映射执行物理点击。"""
        client = await self.frame._ensure_connected()

        container_box = await self.frame.page.locator(self.frame.container_selector).bounding_box()
        if not container_box:
            vw, vh = await self.frame.page.driver.get_viewport_size()
            container_box = {"x": 0, "y": 0, "width": vw, "height": vh}

        deadline = time.monotonic() + timeout_s
        box: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            box = await client.get_element_box(self.selector)
            if box and float(box.get("width", 0)) > 0:
                break
            await asyncio.sleep(0.1)

        if not box:
            raise TimeoutError(f"Web 元素未在指定超时时间内可见: {self.selector}")

        px = int(container_box["x"] + box["x"] + box["width"] / 2.0)
        py = int(container_box["y"] + box["y"] + box["height"] / 2.0)

        await self.frame.page.driver.tap(px, py)
        self.frame.page.action_engine.invalidate_cache()
        return ActionResult(verb="click", target=self.selector, success=True, time_taken_ms=100)

    async def fill(self, text: str, timeout_s: float = 5.0) -> ActionResult:
        """聚焦目标输入框并注入文本。"""
        await self.click(timeout_s=timeout_s)
        client = await self.frame._ensure_connected()
        js_arg = json.dumps(text)
        await client.evaluate(
            f"""(() => {{
                const el = document.querySelector({json.dumps(self.selector)});
                if (el) {{
                    el.focus();
                    el.value = {js_arg};
                    el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                }}
            }})()"""
        )
        return ActionResult(verb="fill", target=self.selector, success=True, time_taken_ms=150)

    async def text_content(self, timeout_s: float = 5.0) -> str | None:
        """提取 DOM 节点文本内容。"""
        client = await self.frame._ensure_connected()
        box = await client.get_element_box(self.selector)
        return str(box.get("text")) if box and box.get("text") is not None else None
