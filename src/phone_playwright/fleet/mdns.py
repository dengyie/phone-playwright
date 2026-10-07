"""mDNS 局域网服务发现器 (MDNS Discovery)。

负责监听与解析 Android 11+ 无线调试广播 (_adb-tls-connect._tcp)，
应对局域网真机因重启或 Wi-Fi 重新连入引发的端口动态漂移。
"""

from __future__ import annotations
import asyncio
import re
from typing import Dict, List


class MdnsServiceInfo:
    """发现的 mDNS 服务信息。"""

    def __init__(self, service_name: str, ip: str, port: int) -> None:
        self.service_name = service_name
        self.ip = ip
        self.port = port

    @property
    def address(self) -> str:
        return f"{self.ip}:{self.port}"

    def __repr__(self) -> str:
        return f"<MdnsServiceInfo {self.service_name} at {self.address}>"


class MdnsDiscovery:
    """mDNS 设备广播发现器。"""

    def __init__(self, adb_path: str = "adb") -> None:
        self.adb_path = adb_path

    async def discover_services(self, timeout_s: float = 3.0) -> list[MdnsServiceInfo]:
        """通过 ADB 本地守护进程查询已发现的 mDNS 服务。"""
        try:
            proc = await asyncio.create_subprocess_exec(
                self.adb_path, "mdns", "services",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except (asyncio.TimeoutError, Exception):
            return []

        lines = stdout.decode("utf-8", errors="replace").strip().splitlines()
        discovered: list[MdnsServiceInfo] = []

        # 示例输出匹配:
        # adb-xxx-yyy  _adb-tls-connect._tcp.  192.168.1.3:43037
        for line in lines:
            line = line.strip()
            if "_adb-tls-connect._tcp" in line or "_adb._tcp" in line:
                match = re.search(r"(\d+\.\d+\.\d+\.\d+):(\d+)", line)
                if match:
                    ip = match.group(1)
                    port = int(match.group(2))
                    parts = line.split()
                    svc_name = parts[0] if parts else "unknown"
                    discovered.append(MdnsServiceInfo(service_name=svc_name, ip=ip, port=port))

        return discovered

    async def find_port_for_ip(self, target_ip: str, timeout_s: float = 3.0) -> int | None:
        """为特定 IP 查询最新漂移后的连接端口。"""
        services = await self.discover_services(timeout_s=timeout_s)
        for svc in services:
            if svc.ip == target_ip:
                return svc.port
        return None
