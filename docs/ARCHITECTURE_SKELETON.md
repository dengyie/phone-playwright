# Phone-Playwright: 架构层、代码层、数据层完整规格说明书 (Architecture Skeleton)

本文档是 `phone-playwright` 项目的核心技术骨架规范，严格规范系统在**架构层（Architecture）**、**代码层（Code）**、**数据层（Data）**的三层设计标准，作为后续所有代码实现和测试用例验收的唯一定义源（Single Source of Truth）。

---

## 第一部分：架构层规范 (Architecture Layer)

架构层定义系统的运行时模型、并发调度、状态生命周期、容错机制与物理边界。

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 AI 宿主环境 (AI Host Agent)                                  │
│                 (ZCode / Claude Code / Cursor / Autonomous Agent Loop)                      │
└──────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                               │ MCP (STDIO / SSE) 或 Python/TS In-Process SDK
┌──────────────────────────────────────────────▼──────────────────────────────────────────────┐
│                               架构层边界 1: 协议与会话网关 (Gateway)                           │
│  - MCP Protocol Handler (JSON-RPC 2.0 映射)                                                 │
│  - Session Manager (租户隔离、设备会话生命周期绑定、超时回收)                                 │
└──────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                               │
┌──────────────────────────────────────────────▼──────────────────────────────────────────────┐
│                               架构层边界 2: 核心编排引擎 (Core Engine)                        │
│                                                                                             │
│  ┌───────────────────────────────────┐               ┌───────────────────────────────────┐  │
│  │   双模式运行栈 (Dual Runtime)     │               │    容错与错误屏障 (Error Barrier) │  │
│  │   - Async Core (asyncio 事件驱动) │               │    - DeviceOfflineError 自动恢复  │  │
│  │   - Sync Wrapper (线程桥接封装)   │               │    - ActionabilityTimeout 重试    │  │
│  └───────────────────────────────────┘               └───────────────────────────────────┘  │
│                                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                            设备舰队生命周期调度器 (Fleet Manager)                       │  │
│  │  - mDNS 发现器 (监听 `_adb-tls-connect._tcp` 广播)                                     │  │
│  │  - 状态探活与看门狗线程 (Watchdog: 10s PING / 端口漂移自动重绑)                        │  │
│  │  - 设备互斥锁 (Device Mutex: 保证多 Agent 并发时不冲突操作同一屏幕)                   │  │
│  └───────────────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                               │ 抽象驱动契约 (IDriver Interface)
┌──────────────────────────────────────────────▼──────────────────────────────────────────────┐
│                               架构层边界 3: 物理驱动适配层 (Driver Layer)                     │
│                                                                                             │
│        ┌──────────────────────────────────┐        ┌──────────────────────────────────┐     │
│        │          AndroidDriver           │        │            IOSDriver             │     │
│        │  - RPC 通道: uiautomator2 / adb  │        │  - HTTP REST: WebDriverAgent     │     │
│        │  - 屏幕通道: Minicap / Screencap │        │  - 屏幕通道: WDA /screenshot     │     │
│        │  - 输入通道: FastInputIME (无键盘)│       │  - 输入通道: WDA /wda/keys       │     │
│        └──────────────────────────────────┘        └──────────────────────────────────┘     │
└──────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                               │ LAN (Wi-Fi 局域网) / USB
┌──────────────────────────────────────────────▼──────────────────────────────────────────────┐
│                               架构层边界 4: 硬件设备集群 (Physical Devices)                  │
│       [OnePlus 7T: 192.168.1.3]       [Android #2: 192.168.1.4]        [iPhone 13 (未来)]   │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.1 并发与异步模型
- **核心内核基于 `asyncio`**：感知（Dump 树）、网络传输、心跳探测、Auto-waiting 轮询全部由 Python `asyncio` 原生驱动，单进程可轻松支撑 10+ 台局域网手机的高并发轮询。
- **双模 API 导出**：
  - `phone_playwright.async_api`：供高性能服务端、MCP Server、异步 Agent 框架使用。
  - `phone_playwright.sync_api`：通过内部创建专用后台事件循环（EventLoop in Background Thread）封装为阻塞式调用，供简单自动化脚本和调试 REPL 极简使用。

### 1.2 设备看门狗与自愈管道 (Watchdog Self-Healing Pipeline)
针对 Android 无线调试的端口漂移与 Wi-Fi 睡眠断连：
1. **心跳探针**：每 10 秒向 `device.serial` 发送轻量命令（如 `getprop sys.boot_completed`）。
2. **断连感知**：若连续 2 次超时，将设备标记为 `STALE`。
3. **mDNS 再发现**：看门狗调用本地 mDNS 缓存，匹配设备的 MAC 或持久硬件 ID，拉取最新动态端口并执行 `adb connect <ip>:<new_port>`。
4. **透明重试**：如果动作正在执行途中遭遇断连，Auto-waiting 引擎在超时窗口内挂起动作，等待看门狗 3 秒内恢复链路后自动继续执行，不直接对 AI 报错。

### 1.3 错误屏障体系 (Error Barriers)
全系统统一异常分类，确保向 AI 返回的错误信息结构化、具象化且包含指导建议：

| 异常类 | 触发场景 | AI 看到的上下文建议 |
| :--- | :--- | :--- |
| `DeviceOfflineError` | 物理设备掉线或网络不可达 | "设备离线，检查局域网连接或重新配对" |
| `ActionabilityTimeoutError`| 元素在规定超时内未稳定、不可见或未使能 | "元素在 5s 内未能达到可交互状态（可能正在加载或被遮挡）" |
| `SelectorNotFoundError` | 树中完全不存在匹配该选择器的节点 | "未找到元素，请根据最新 snapshot 重新获取 @ref" |
| `OffscreenElementError` | 元素完全超出屏幕可视物理视口 | "目标在屏幕外，需先调用 swipe 滚动至视口内" |

---

## 第二部分：数据层规范 (Data Layer)

数据层定义全流程流转的强类型模式（Schema），使用 Pydantic / TypedDict 严格约束。

```
[设备原始数据 (Raw Dump)]
       │
       ▼ (Parser)
[RawNode 树 (标准化内存树)] ───► [设备视口几何 (Viewport)]
       │
       ▼ (Pruning & Viewport Clipping & Hoisting)
[CompactElement 列表 (精炼元素清单)]
       │
       ├─────────────────────────────────────────┐
       ▼                                         ▼
[PageSnapshot 快照数据]                   [LLM 表现层 (Markdown/@ref)]
(用于缓存、断言、高阶过滤)               (用于 Prompt 注入与 Token 极致压缩)
```

### 2.1 基础几何模式 (`geometry.py`)
```python
from pydantic import BaseModel, Field

class Rect(BaseModel):
    left: int = Field(..., description="左上角 X 像素")
    top: int = Field(..., description="左上角 Y 像素")
    right: int = Field(..., description="右下角 X 像素")
    bottom: int = Field(..., description="右下角 Y 像素")

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center(self) -> tuple[int, int]:
        return ((self.left + self.right) // 2, (self.top + self.bottom) // 2)

    def intersects(self, other: "Rect") -> bool:
        return not (self.right <= other.left or self.left >= other.right or
                    self.bottom <= other.top or self.top >= other.bottom)

    def intersection(self, other: "Rect") -> "Rect | None":
        if not self.intersects(other):
            return None
        return Rect(
            left=max(self.left, other.left),
            top=max(self.top, other.top),
            right=min(self.right, other.right),
            bottom=min(self.bottom, other.bottom)
        )
```

### 2.2 原始节点模式 (`raw_node.py`)
无论是 Android 的 XML 转译还是 iOS 的 JSON 转译，进入核心前必须对齐为 `RawNode`：
```python
class RawNode(BaseModel):
    id: str = Field(default="", description="原生资源 ID (如 com.app:id/btn)")
    class_name: str = Field(..., description="原生类名")
    text: str | None = None
    desc: str | None = Field(default=None, description="无障碍标签描述")
    bounds: Rect
    clickable: bool = False
    editable: bool = False
    scrollable: bool = False
    enabled: bool = True
    visible: bool = True
    children: list["RawNode"] = Field(default_factory=list)
```

### 2.3 紧凑语义元素模式 (`compact_element.py`)
蒸馏算法输出的标准元素对象，杜绝一切冗余嵌套：
```python
from typing import Literal

SemanticRole = Literal[
    "button", "input", "item", "text", "image", 
    "tab", "checkbox", "switch", "scrollable", "unknown"
]

class CompactElement(BaseModel):
    ref: str | None = Field(None, description="唯一交互编号，如 '@1'。仅交互元素拥有")
    role: SemanticRole = Field(..., description="推断出的无障碍语义角色")
    text: str = Field(..., description="提取并合并后的核心文本/标签")
    bounds: Rect = Field(..., description="物理绝对像素边界")
    enabled: bool = True
    scrollable: bool = False
    raw_resource_id: str | None = None
```

### 2.4 页面快照模式 (`snapshot.py`)
```python
class PageSnapshot(BaseModel):
    timestamp: float
    device_id: str
    package_name: str | None = None
    activity_name: str | None = None
    viewport_width: int
    viewport_height: int
    elements: list[CompactElement]
    
    def to_markdown(self) -> str:
        """为 LLM 生成最少 Token、最高信息密度的纯文本输入"""
        lines = [f"# Device Viewport: {self.viewport_width}x{self.viewport_height}"]
        if self.package_name:
            lines.append(f"# Active App: {self.package_name}")
        lines.append("## Interactive Elements:")
        for el in self.elements:
            if el.ref:
                lines.append(f"- [{el.ref}] {el.role}: \"{el.text}\"")
            else:
                lines.append(f"- (info) {el.role}: \"{el.text}\"")
        return "\n".join(lines)
```

### 2.5 动作载荷与结果模式 (`action.py`)
```python
ActionVerb = Literal["click", "fill", "swipe", "press_key", "tap_coord"]

class ActionPayload(BaseModel):
    verb: ActionVerb
    target: str | None = Field(None, description="如 '@1' 或 'text=搜索'")
    value: str | None = Field(None, description="输入文本或滑动方向")
    timeout_s: float = 5.0

class ActionResult(BaseModel):
    success: bool
    verb: str
    target: str | None
    executed_at_bounds: Rect | None = None
    time_taken_ms: int
    error: str | None = None
```

---

## 第三部分：代码层规范 (Code Layer)

代码层定义代码仓库的文件物理组织、核心类依赖倒置（DIP）和协作关系。

### 3.1 项目目录树规划
```
phone-playwright/
├── docs/                             # 开发设计与规范文档 (已创建)
│   ├── ARCHITECTURE_SKELETON.md      # [本规范书] 架构/代码/数据层全景骨架
│   ├── DESIGN.md                     # 系统架构与哲学
│   ├── ALGORITHMS.md                 # 剪枝与 Auto-waiting 状态机算法
│   ├── API_SPEC.md                   # SDK 与 MCP 协议详细规范
│   └── FLEET_AND_DRIVERS.md          # 局域网集群与跨平台驱动
├── src/
│   └── phone_playwright/
│       ├── __init__.py               # 暴露 sync_api 和 async_api
│       ├── core/                     # 核心领域逻辑 (与平台无关)
│       │   ├── __init__.py
│       │   ├── pruner.py             # Viewport-aware 树剪枝器
│       │   ├── state_machine.py      # Actionability & Auto-waiting 状态机
│       │   ├── locator.py            # Locator 实现与延迟解析器
│       │   └── selector.py           # 选择器解析 (Ref, Text, Role, ID)
│       ├── models/                   # 数据层强类型模型
│       │   ├── __init__.py
│       │   ├── geometry.py           # Rect, Viewport
│       │   ├── schema.py             # RawNode, CompactElement, PageSnapshot
│       │   └── actions.py            # ActionPayload, ActionResult
│       ├── drivers/                  # 硬件驱动抽象与实现
│       │   ├── __init__.py
│       │   ├── base.py               # BaseDriver (抽象基类)
│       │   ├── android.py            # AndroidDriver (u2 / adb-tls)
│       │   └── ios.py                # IOSDriver (WDA 适配器)
│       ├── fleet/                    # 集群与设备管理
│       │   ├── __init__.py
│       │   ├── manager.py            # FleetManager 设备池
│       │   ├── mdns.py               # mDNS 局域网服务发现
│       │   └── watchdog.py           # 探活与自愈守护线程
│       ├── mcp/                      # Model Context Protocol 服务端
│       │   ├── __init__.py
│       │   ├── server.py             # MCP Server 入口
│       │   └── tools.py              # 工具映射定义
│       └── api/                      # 面向开发者的 SDK
│           ├── __init__.py
│           ├── sync_api.py           # 同步 API 门面
│           └── async_api.py          # 异步 API 门面
├── tests/                            # 自动化测试矩阵
│   ├── test_geometry.py              # 几何计算与交集单测
│   ├── test_pruner.py                # 视口裁剪与树蒸馏断言测试
│   ├── test_state_machine.py         # 状态机 Auto-waiting 单测
│   └── test_live_oneplus7t.py        # 现场真机集成冒烟测试 (OnePlus 7T)
├── pyproject.toml                    # 依赖管理 (poetry / flit)
└── README.md
```

### 3.2 核心抽象契约定义

#### 驱动基类契约 (`drivers/base.py`)
```python
from abc import ABC, abstractmethod
from phone_playwright.models.geometry import Rect
from phone_playwright.models.schema import RawNode

class BaseDriver(ABC):
    @abstractmethod
    async def connect(self) -> None:
        """建立连接"""

    @abstractmethod
    async def disconnect(self) -> None:
        """释放底层句柄"""

    @abstractmethod
    async def get_viewport_size(self) -> tuple[int, int]:
        """获取物理分辨率 (宽, 高)"""

    @abstractmethod
    async def dump_raw_tree(self) -> RawNode:
        """拉取平台原始数据并归一化为 RawNode 根节点"""

    @abstractmethod
    async def tap(self, x: int, y: int) -> None:
        """下发绝对坐标点击"""

    @abstractmethod
    async def type_text(self, text: str) -> None:
        """键入文本"""

    @abstractmethod
    async def swipe(self, sx: int, sy: int, ex: int, ey: int, duration_ms: int = 300) -> None:
        """滑动手势"""

    @abstractmethod
    async def take_screenshot(self) -> bytes:
        """截屏字节流"""
```

#### 定位器核心契约 (`core/locator.py`)
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from phone_playwright.api.async_api import AsyncPhonePage

class PhoneLocator:
    def __init__(self, page: "AsyncPhonePage", selector_str: str):
        self._page = page
        self._selector_str = selector_str

    async def click(self, timeout_s: float = 5.0) -> None:
        """通过 Actionability 状态机执行点击"""
        await self._page._action_engine.execute(
            verb="click", target=self._selector_str, timeout_s=timeout_s
        )

    async def fill(self, text: str, timeout_s: float = 5.0) -> None:
        """通过 Actionability 状态机聚焦并填充文本"""
        await self._page._action_engine.execute(
            verb="fill", target=self._selector_str, value=text, timeout_s=timeout_s
        )
```

---

## 第四部分：各层之间的调用序列图 (Interaction Sequence)

### AI 触发一次 `page.locator("@2").click()` 的内部全流程：

```
AI Agent         PhoneLocator       ActionEngine        Pruner          AndroidDriver      OnePlus 7T
   │                  │                  │                 │                  │                │
   │── click() ──────►│                  │                 │                  │                │
   │                  │── execute() ────►│                 │                  │                │
   │                  │                  │                                    │                │
   │                  │                  │─── 1. dump_raw_tree() ────────────►│── RPC Dump ───►│
   │                  │                  │◄── RawNode ────────────────────────│◄── XML ────────│
   │                  │                  │                                    │                │
   │                  │                  │─── 2. prune(RawNode, Viewport) ───►│                │
   │                  │                  │◄── [CompactElement] (含 @2) ───────│                │
   │                  │                  │                                    │                │
   │                  │                  │─── 3. Actionability Checks ────────│                │
   │                  │                  │       - Attached? OK               │                │
   │                  │                  │       - In Viewport? OK            │                │
   │                  │                  │       - Stable? (采样间隔200ms) OK │                │
   │                  │                  │       - Enabled? OK                │                │
   │                  │                  │                                    │                │
   │                  │                  │─── 4. 计算 @2 中心点 (cx, cy)      │                │
   │                  │                  │                                    │                │
   │                  │                  │─── 5. tap(cx, cy) ────────────────►│── adb tap ────►│
   │                  │                  │◄── Ack ────────────────────────────│◄── OK ─────────│
   │                  │◄── Complete ─────│                                    │                │
   │◄── Success ──────│                  │                                    │                │
```

---

## 第五部分：验收标准矩阵 (Definition of Done)

1. **Token 压缩验收**：
   - 输入：真实 App（如微信、闲鱼、系统设置）页面原生 Dump。
   - 输出：`CompactElement` 结构。
   - 指标：字符量降低 $\ge 90\%$，屏幕外元素消除率达到 $100\%$。
2. **Auto-waiting 稳定性验收**：
   - 在页面存在网络延迟或页面正在滑动的场景下，`locator.click()` 不发生坐标错位空点，等待静止后精准命中目标中心。
3. **多机并发验收**：
   - 在局域网同时驱动 3 台手机（包括当前 `192.168.1.3:43037`），互不阻塞，心跳自动保持。
