"""设备集群自愈看门狗 (Fleet Watchdog)。

负责对注册的局域网无线设备执行周期性心跳探针 (Heartbeat Ping)，
感知端口漂移与 Wi-Fi 深度休眠，并联动 mDNS 执行链路自愈。
"""

from __future__ import annotations
import asyncio
import logging
from typing import Callable, Coroutine, Any
from phone_playwright.fleet.mdns import MdnsDiscovery

logger = logging.getLogger("phone_playwright.watchdog")


class DeviceWatchdog:
    """设备探活与重连自愈看门狗。"""

    def __init__(
        self,
        adb_path: str = "adb",
        check_interval_s: float = 10.0,
        reconnect_callback: Callable[[str, str], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        self.adb_path = adb_path
        self.check_interval_s = check_interval_s
        self.reconnect_callback = reconnect_callback
        self.mdns = MdnsDiscovery(adb_path=adb_path)
        self._monitored_devices: dict[str, dict[str, Any]] = {}
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    def register(self, device_id: str, alias: str | None = None) -> None:
        """登记需守护的目标设备。"""
        self._monitored_devices[device_id] = {
            "alias": alias or device_id,
            "fail_count": 0,
            "status": "online",
        }

    def unregister(self, device_id: str) -> None:
        """移除监视目标。"""
        self._monitored_devices.pop(device_id, None)

    async def start(self) -> None:
        """启动后台看门狗轮询任务。"""
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """停止看门狗轮询任务。"""
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _ping_device(self, device_id: str) -> bool:
        """下发轻量心跳指令测试通道是否活跃。"""
        try:
            proc = await asyncio.create_subprocess_exec(
                self.adb_path, "-s", device_id, "shell", "echo", "1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3.0)
            return proc.returncode == 0 and b"1" in stdout
        except Exception:
            return False

    async def _attempt_recovery(self, device_id: str) -> None:
        """执行自愈重连。若为 IP:PORT 无线设备，借助 mDNS 探测新端口。"""
        if ":" not in device_id:
            # USB 设备直接尝试 reconnect
            try:
                await asyncio.create_subprocess_exec(
                    self.adb_path, "reconnect", "device", device_id,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            except Exception:
                pass
            return

        ip, old_port = device_id.split(":", 1)
        new_port = await self.mdns.find_port_for_ip(ip)
        target_port = new_port if new_port else int(old_port)
        new_device_id = f"{ip}:{target_port}"

        try:
            proc = await asyncio.create_subprocess_exec(
                self.adb_path, "connect", new_device_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            if b"connected" in stdout.lower():
                logger.info(f"Watchdog 成功自愈重连设备: {new_device_id}")
                if new_device_id != device_id:
                    old_info = self._monitored_devices.pop(device_id, {})
                    old_info["fail_count"] = 0
                    old_info["status"] = "online"
                    self._monitored_devices[new_device_id] = old_info
                    if self.reconnect_callback:
                        await self.reconnect_callback(device_id, new_device_id)
                else:
                    if device_id in self._monitored_devices:
                        self._monitored_devices[device_id]["fail_count"] = 0
                        self._monitored_devices[device_id]["status"] = "online"
        except Exception as e:
            logger.debug(f"Watchdog 重连尝试失败: {e}")

    async def _run_loop(self) -> None:
        """看门狗守护循环主流程。"""
        while not self._stop_event.is_set():
            for device_id, info in list(self._monitored_devices.items()):
                alive = await self._ping_device(device_id)
                if alive:
                    info["fail_count"] = 0
                    info["status"] = "online"
                else:
                    info["fail_count"] += 1
                    if info["fail_count"] >= 2:
                        info["status"] = "stale"
                        logger.warning(f"设备 {device_id} 心跳丢失，触发自愈重连管道...")
                        await self._attempt_recovery(device_id)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.check_interval_s)
            except asyncio.TimeoutError:
                continue
