"""设备集群管理器 (FleetManager)。

负责局域网与 USB 设备的发现、心跳保活、端口重连与持久别名路由。
集成并发防重锁，保障多协程同时获取同一设备时的单例安全，
并可挂载 DeviceWatchdog 实现静默自动重连自愈。
"""

from __future__ import annotations
import asyncio
import re
from typing import Dict
from phone_playwright.drivers.base import BaseDriver
from phone_playwright.drivers.android_adb import AndroidAdbDriver
from phone_playwright.drivers.ios_wda import IosWdaDriver
from phone_playwright.models.exceptions import DeviceOfflineError
from phone_playwright.fleet.watchdog import DeviceWatchdog


class FleetManager:
    """局域网设备集群生命周期管理器。"""

    def __init__(self, adb_path: str = "adb") -> None:
        self.adb_path = adb_path
        self._drivers: dict[str, BaseDriver] = {}
        self._alias_map: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._watchdog: DeviceWatchdog | None = None

    async def scan_devices(self) -> list[dict[str, str]]:
        """扫描当前通过 USB 或 Wi-Fi 已连通的所有设备。"""
        proc = await asyncio.create_subprocess_exec(
            self.adb_path, "devices", "-l",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        lines = stdout.decode("utf-8", errors="replace").strip().splitlines()

        found: list[dict[str, str]] = []
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                serial = parts[0]
                model_match = re.search(r"model:(\S+)", line)
                model = model_match.group(1) if model_match else "Android"
                found.append({"serial": serial, "model": model, "status": "online"})
        return found

    def register_alias(self, alias: str, device_id: str) -> None:
        """为设备绑定语义化别名，如 'oneplus-7t' -> '192.168.1.3:43037'。"""
        self._alias_map[alias] = device_id

    async def _handle_device_reconnected(self, old_id: str, new_id: str) -> None:
        """Watchdog 触发端口漂移自愈后的驱动映射更新。"""
        async with self._lock:
            if old_id in self._drivers:
                old_driver = self._drivers.pop(old_id)
                await old_driver.disconnect()
                new_driver: BaseDriver
                if new_id.startswith("http://") or new_id.startswith("https://") or "ios" in new_id.lower():
                    new_driver = IosWdaDriver(device_id=new_id, wda_base_url=new_id)
                else:
                    new_driver = AndroidAdbDriver(device_id=new_id, adb_path=self.adb_path)

                try:
                    await new_driver.connect()
                    self._drivers[new_id] = new_driver
                except Exception:
                    pass

            for alias, target in list(self._alias_map.items()):
                if target == old_id:
                    self._alias_map[alias] = new_id

    def enable_watchdog(self, check_interval_s: float = 10.0) -> DeviceWatchdog:
        """启用后台自愈看门狗。"""
        if self._watchdog is None:
            self._watchdog = DeviceWatchdog(
                adb_path=self.adb_path,
                check_interval_s=check_interval_s,
                reconnect_callback=self._handle_device_reconnected,
            )
        return self._watchdog

    async def get_driver(self, alias_or_id: str) -> BaseDriver:
        """并发安全地获取或创建指定设备的驱动实例。支持 Android ADB 与 iOS WDA 驱动动态分发。"""
        real_id = self._alias_map.get(alias_or_id, alias_or_id)

        async with self._lock:
            if real_id in self._drivers:
                return self._drivers[real_id]

            driver: BaseDriver
            if real_id.startswith("http://") or real_id.startswith("https://") or "ios" in alias_or_id.lower() or "ios" in real_id.lower():
                driver = IosWdaDriver(device_id=real_id, wda_base_url=real_id)
            else:
                driver = AndroidAdbDriver(device_id=real_id, adb_path=self.adb_path)

            try:
                await driver.connect()
            except Exception as e:
                raise DeviceOfflineError(real_id, str(e)) from e

            if driver.device_id and driver.device_id != real_id:
                self._drivers[driver.device_id] = driver
                self._alias_map[alias_or_id] = driver.device_id
                real_id = driver.device_id

            self._drivers[real_id] = driver
            if self._watchdog and isinstance(driver, AndroidAdbDriver):
                self._watchdog.register(real_id, alias=alias_or_id)
            return driver

    async def close_all(self) -> None:
        """安全释放所有设备句柄与看门狗。"""
        if self._watchdog:
            await self._watchdog.stop()

        async with self._lock:
            for driver in self._drivers.values():
                try:
                    await driver.disconnect()
                except Exception:
                    pass
            self._drivers.clear()
