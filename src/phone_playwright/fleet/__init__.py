"""设备集群管理与发现模块。"""

from phone_playwright.fleet.manager import FleetManager
from phone_playwright.fleet.mdns import MdnsDiscovery, MdnsServiceInfo
from phone_playwright.fleet.watchdog import DeviceWatchdog

__all__ = ["FleetManager", "MdnsDiscovery", "MdnsServiceInfo", "DeviceWatchdog"]
