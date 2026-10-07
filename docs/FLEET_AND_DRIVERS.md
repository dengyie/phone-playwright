# 多设备集群管理与跨平台适配设计 (Fleet & Drivers)

## 1. 局域网多设备集群管理 (Fleet Manager)

### 1.1 局域网 Wi-Fi 调试的核心痛点
在局域网多测试机（如 3 台真机）环境下，无线调试存在两大典型工程难题：
1. **端口动态漂移**：Android 11+ 无线调试每次开关或重启后，其 TLS 配对端口会动态变化（如从 `43037` 漂移到其他高位端口）。
2. **锁屏休眠与 TCP 断连**：国产系统（ColorOS、MIUI 等）在锁屏若干分钟后，系统省电策略会关闭 Wi-Fi 链路或挂起后台 adbd，导致主机端连接超时。

### 1.2 设备连接池与心跳守望者 (Watchdog) 机制
```
┌────────────────────────────────────────────────────────┐
│               Fleet Manager Watchdog 轮询               │
│                                                        │
│  [mDNS 服务发现] ───► 解析 _adb-tls-connect._tcp 广播   │
│         │                                              │
│         ▼                                              │
│  [设备指纹匹配] ───► 根据 IMEI/MAC/设备型号 绑定持久别名│
│         │            (如 192.168.1.3 -> "phone-oneplus")│
│         ▼                                              │
│  [心跳保活探测] ───► 每 10s 发送轻量 ADB Ping           │
│         │            若离线则自动重试连接最新端口       │
│         ▼                                              │
│  [就绪连接池]   ───► 提供给 AI 调度: fleet.get("phone-1")│
└────────────────────────────────────────────────────────┘
```

#### 设备注册配置示例 (`devices.yaml`)
```yaml
fleet:
  devices:
    - alias: "oneplus-7t-main"
      model: "HD1900"
      ip: "192.168.1.3"
      platform: "android"
      keep_alive: true
      default_role: "crawler"

    - alias: "android-sub-02"
      model: "Xiaomi 10"
      ip: "192.168.1.4"
      platform: "android"
      keep_alive: true

    - alias: "iphone-13-dev"
      model: "iPhone 13"
      platform: "ios"
      wda_url: "http://192.168.1.5:8100"
      keep_alive: false
```

---

## 2. 跨平台 Driver 适配架构

为了确保未来平滑无缝接入 iPhone，上层核心引擎与底层通信彻底隔离，通过抽象基类 `BaseDriver` 约束行为。

### 2.1 统一 Driver 契约规范

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BaseDriver(ABC):
    @abstractmethod
    def connect(self) -> None:
        """建立底层连接"""
        pass

    @abstractmethod
    def get_raw_hierarchy(self) -> str:
        """获取底层原始页面树 (XML 或 JSON)"""
        pass

    @abstractmethod
    def get_viewport_size(self) -> tuple[int, int]:
        """获取当前视口的物理宽高像素"""
        pass

    @abstractmethod
    def tap(self, x: int, y: int) -> None:
        """触发绝对坐标点击"""
        pass

    @abstractmethod
    def type_text(self, text: str) -> None:
        """在当前焦点控件输入文本"""
        pass

    @abstractmethod
    def swipe(self, sx: int, sy: int, ex: int, ey: int, duration_ms: int = 300) -> None:
        """滑动屏幕"""
        pass

    @abstractmethod
    def take_screenshot(self) -> bytes:
        """抓取物理屏幕图像"""
        pass
```

### 2.2 Android 驱动实现细节 (`AndroidDriver`)
- **底层通信**：使用 `uiautomator2` 或原生 `adb -s <ip:port>` RPC 桥接。
- **原始数据源**：调用 `device.dump_hierarchy(compressed=False)`。
- **输入法优化**：启用轻量虚拟输入法（如 FastInputIME），防止原生软键盘弹出破坏视口布局。

### 2.3 iOS 驱动实现细节 (`IOSDriver`)
- **底层通信**：通过局域网 HTTP 协议直接与 iOS 机器上的 **WebDriverAgent (WDA)** 通信。
- **原始数据源**：调用 WDA 的 `GET /source?format=json`，获取原生的 iOS XCTest 节点树。
- **手势注入**：调用 WDA 的 `POST /wda/tap/nil` 与 `POST /wda/keys`。
- **兼容性保障**：由于 `prune_and_distill` 算法只依赖坐标外接矩形和文本描述，iOS 的 JSON 树经过字段适配器后，完全可以喂给同一个剪枝算法，产出结构一致的 `@ref` 紧凑树给 AI。
