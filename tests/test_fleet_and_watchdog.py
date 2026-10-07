"""设备集群、mDNS 发现与自愈看门狗测试。"""

import pytest
import asyncio
from phone_playwright.fleet.mdns import MdnsDiscovery, MdnsServiceInfo
from phone_playwright.fleet.watchdog import DeviceWatchdog
from phone_playwright.fleet.manager import FleetManager
from phone_playwright.drivers.base import BaseDriver
from phone_playwright.models.schema import RawNode
from phone_playwright.models.geometry import Rect


class DummyFleetDriver(BaseDriver):
    def __init__(self, device_id: str) -> None:
        super().__init__(device_id)
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def get_viewport_size(self) -> tuple[int, int]:
        return (1080, 2400)

    async def dump_raw_tree(self) -> RawNode:
        return RawNode(
            class_name="android.widget.FrameLayout",
            bounds=Rect(left=0, top=0, right=1080, bottom=2400),
        )

    async def tap(self, x: int, y: int) -> None:
        pass

    async def type_text(self, text: str) -> None:
        pass

    async def swipe(self, sx: int, sy: int, ex: int, ey: int, duration_ms: int = 300) -> None:
        pass

    async def long_press(self, x: int, y: int, duration_ms: int = 800) -> None:
        pass

    async def press_key(self, key: str | int) -> None:
        pass

    async def take_screenshot(self) -> bytes:
        return b""

    async def get_current_app(self) -> tuple[str | None, str | None]:
        return None, None


@pytest.mark.asyncio
async def test_mdns_discovery_parsing(monkeypatch):
    mdns = MdnsDiscovery(adb_path="adb")

    sample_output = (
        b"List of discovered mdns services\n"
        b"adb-1234-abcd\t_adb-tls-connect._tcp.\t192.168.1.3:43037\n"
        b"adb-5678-efgh\t_adb-tls-connect._tcp.\t192.168.1.4:38821\n"
    )

    async def fake_proc(*args, **kwargs):
        class FakeProcess:
            returncode = 0
            async def communicate(self):
                return sample_output, b""
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_proc)

    services = await mdns.discover_services()
    assert len(services) == 2
    assert services[0].ip == "192.168.1.3"
    assert services[0].port == 43037
    assert services[1].ip == "192.168.1.4"
    assert services[1].port == 38821

    port = await mdns.find_port_for_ip("192.168.1.3")
    assert port == 43037


@pytest.mark.asyncio
async def test_fleet_manager_aliases_and_caching(monkeypatch):
    fleet = FleetManager(adb_path="adb")
    fleet.register_alias("oneplus-7t", "192.168.1.3:43037")

    driver_map: dict[str, DummyFleetDriver] = {}

    def fake_driver_factory(device_id: str, adb_path: str = "adb"):
        if device_id not in driver_map:
            driver_map[device_id] = DummyFleetDriver(device_id)
        return driver_map[device_id]

    monkeypatch.setattr("phone_playwright.fleet.manager.AndroidAdbDriver", fake_driver_factory)

    driver1 = await fleet.get_driver("oneplus-7t")
    driver2 = await fleet.get_driver("192.168.1.3:43037")

    # 别名与实际 IP:Port 应当命中同一个驱动单例实例
    assert driver1 is driver2
    assert isinstance(driver1, DummyFleetDriver)
    assert driver1.device_id == "192.168.1.3:43037"
    assert driver1.connected is True

    await fleet.close_all()
    assert driver1.connected is False


@pytest.mark.asyncio
async def test_watchdog_monitoring():
    reconnect_events: list[tuple[str, str]] = []

    async def fake_reconnect_cb(old_id: str, new_id: str):
        reconnect_events.append((old_id, new_id))

    watchdog = DeviceWatchdog(
        adb_path="adb",
        check_interval_s=0.1,
        reconnect_callback=fake_reconnect_cb,
    )

    watchdog.register("192.168.1.3:43037", alias="phone-1")
    assert "192.168.1.3:43037" in watchdog._monitored_devices

    # 模拟探测成功
    async def mock_ping_success(device_id: str) -> bool:
        return True

    watchdog._ping_device = mock_ping_success  # type: ignore[method-assign]
    await watchdog.start()
    await asyncio.sleep(0.25)
    await watchdog.stop()

    info = watchdog._monitored_devices["192.168.1.3:43037"]
    assert info["status"] == "online"
    assert info["fail_count"] == 0


@pytest.mark.asyncio
async def test_watchdog_port_drift_migration_atomic(monkeypatch):
    """验证看门狗在感知到端口漂移自愈连接成功后，原子迁移内部 monitored_devices 键，避免死循环。"""
    reconnect_events: list[tuple[str, str]] = []

    async def fake_reconnect_cb(old_id: str, new_id: str):
        reconnect_events.append((old_id, new_id))

    watchdog = DeviceWatchdog(
        adb_path="adb",
        check_interval_s=0.1,
        reconnect_callback=fake_reconnect_cb,
    )
    old_dev = "192.168.1.3:43037"
    new_dev = "192.168.1.3:55555"

    watchdog.register(old_dev, alias="oneplus-7t")

    # 模拟 mDNS 返回新端口
    async def fake_find_port(target_ip: str, timeout_s: float = 3.0) -> int | None:
        return 55555

    monkeypatch.setattr(watchdog.mdns, "find_port_for_ip", fake_find_port)

    # 模拟 adb connect 成功输出
    async def fake_proc(*args, **kwargs):
        class FakeProcess:
            returncode = 0
            async def communicate(self):
                return b"connected to 192.168.1.3:55555", b""
        return FakeProcess()

    import phone_playwright.fleet.watchdog as wd_mod
    orig_subprocess = asyncio.create_subprocess_exec

    try:
        asyncio.create_subprocess_exec = fake_proc  # type: ignore[assignment]
        await watchdog._attempt_recovery(old_dev)

        # 验证旧键已出队，新键已入队且状态重置为 online
        assert old_dev not in watchdog._monitored_devices
        assert new_dev in watchdog._monitored_devices
        assert watchdog._monitored_devices[new_dev]["status"] == "online"
        assert watchdog._monitored_devices[new_dev]["fail_count"] == 0
        assert reconnect_events == [(old_dev, new_dev)]
    finally:
        asyncio.create_subprocess_exec = orig_subprocess


@pytest.mark.asyncio
async def test_fleet_manager_ios_driver_dispatch(monkeypatch):
    """验证 FleetManager 对 iOS WDA / HTTP 路径的动态分发能力。"""
    fleet = FleetManager(adb_path="adb")

    class DummyIosDriver(DummyFleetDriver):
        def __init__(self, device_id: str, wda_base_url: str):
            super().__init__(device_id)
            self.wda_base_url = wda_base_url

    monkeypatch.setattr("phone_playwright.fleet.manager.IosWdaDriver", DummyIosDriver)

    ios_driver = await fleet.get_driver("http://192.168.1.50:8100")
    assert isinstance(ios_driver, DummyIosDriver)
    assert ios_driver.device_id == "http://192.168.1.50:8100"
    assert ios_driver.connected is True

