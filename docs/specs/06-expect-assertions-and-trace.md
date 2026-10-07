# Phone-Playwright 异步断言库与 Trace Viewer 规格书 (Expect & Trace)

## 1. 业务痛点与技术诉求

1. **测试脚本脆弱（Flaky Tests）**：传统移动端测试使用裸 `assert locator.is_visible()`，遇到网络延迟、动画未完成时容易瞬间失败，缺乏内置的重试轮询状态机。
2. **失败诊断困难**：AI Agent 或自动化用例在夜间执行失败时，仅有一行错误堆栈，开发者无法复盘执行前后的界面状态、点击热点、网络流转及元素属性变化。

---

## 2. 异步断言库设计 (`expect`)

对齐 Playwright Web 规范，`phone-playwright` 提供原生内置轮询自旋的异步断言库 `expect(...)`。

### 2.1 轮询自旋与单调时钟模型 (Polling Spin State Machine)
断言函数不是单次执行，而是在配置的超时时间（默认 $5.0\text{s}$）内，以指数退避/固定步长（默认 $100\text{ms}$）在 `time.monotonic()` 单调时钟驱动下持续自旋重试，直到条件满足或超时触发。

```
[expect(locator).to_be_visible()]
             |
             v
   [Start Monotonic Clock: deadline = now + timeout_s]
             |
             +<------------------------------------------+
             |                                           |
             v                                           |
   [Evaluate Locator Property]                           |
   (复用 1.0s TTL 温热缓存或拉取最新视口)                   |
             |                                           |
     +-------+-------+                                   |
     | 条件是否达成?  |                                   |
     +-------+-------+                                   |
        /         \                                      |
      Yes          No                                    |
      /              \                                   |
   (Return)     [now >= deadline?]                       |
                   /          \                          |
                 Yes           No                        |
                 /               \                       |
     +--------------------+   [Sleep 100ms]              |
     | 抛出 AssertionError|          |                   |
     | 附带最后一次快照差异  +----------+-------------------+
     +--------------------+
```

### 2.2 核心断言 API 契约
```python
class AsyncExpect:
    def __init__(self, target: PhoneLocator, timeout_s: float = 5.0) -> None:
        self._target = target
        self._timeout_s = timeout_s

    async def to_be_visible(self) -> None:
        """断言目标元素在视口内可见。"""

    async def to_be_hidden(self) -> None:
        """断言目标元素隐藏或已从树中脱离。"""

    async def to_have_text(self, expected: str | re.Pattern) -> None:
        """断言目标元素文本完全匹配预期字符串或正则。"""

    async def to_contain_text(self, expected: str) -> None:
        """断言目标元素文本包含指定子串。"""

    async def to_have_count(self, expected: int) -> None:
        """断言当前视口内匹配该选择器的元素总数等于 expected。"""

    async def to_be_enabled(self) -> None:
        """断言目标元素处于使能可用状态。"""

    async def to_be_disabled(self) -> None:
        """断言目标元素处于禁用置灰状态。"""

def expect(target: PhoneLocator, timeout_s: float = 5.0) -> AsyncExpect:
    """构建异步断言上下文。"""
    return AsyncExpect(target=target, timeout_s=timeout_s)
```

---

## 3. Playwright 兼容 Trace Viewer 录制架构

### 3.1 Trace 包目录结构 (`trace.zip`)
Trace 录制器在自动化会话期间以零性能损耗流式落盘事件与帧，最后打包为标准的 `trace.zip`：
```
trace.zip
├── manifest.json              # 录制元信息 (设备、分辨率、会话起止时间)
├── trace.trace                # JSONL 时序事件流 (动作、耗时、点击坐标、网络)
├── resources/                 # 静态资源池 (按 SHA-256 存储)
│   ├── sha256_before_click.png
│   ├── sha256_after_click.png
│   └── sha256_snapshot_tree.json
└── snapshots/                 # 各关键帧的高对比度 SoM 标注快照
```

### 3.2 动作时间线记录规范 (Trace Event Schema)
```json
{
  "type": "action",
  "name": "click",
  "timestamp": 1728362400.125,
  "duration_ms": 142,
  "selector": "text=应用宝",
  "matched_bounds": {"left": 172, "top": 307, "right": 328, "bottom": 419},
  "click_point": {"x": 250, "y": 363},
  "snapshot_before": "resources/sha256_before.png",
  "snapshot_after": "resources/sha256_after.png",
  "result": {
    "success": true,
    "active_app_after": "com.tencent.android.qqdownloader"
  }
}
```

### 3.3 Trace API 契约与使用范式
```python
async with async_phone_playwright() as pp:
    dev = await pp.connect("10.144.144.51:5555")
    # 开启 Trace 录制 (截图、动作、快照)
    await dev.tracing.start(screenshots=True, snapshots=True)

    page = dev.current_page()
    await page.get_by_text("应用宝").click()
    await expect(page.get_by_text("搜索")).to_be_visible()

    # 停止并导出为标准 trace.zip
    await dev.tracing.stop(path="artifacts/run-1-trace.zip")
```

---

## 4. 离线可视化与 Agent 回溯价值

1. **直接拖拽复盘**：导出的 `trace.zip` 可直接在 Playwright 官方 Web Trace Viewer 或本地内嵌 HTML 查看器中打开，提供逐帧动画、前后对比、网络瀑布流与点击热点。
2. **Agent 自省与自愈 (Self-Reflection)**：当 Agent 执行失败时，将失败步骤的 `snapshot_before` 与 `snapshot_after` 差异输入大模型，Agent 可清晰感知动作导致的状态转移（如点击后弹出广告弹窗还是直接崩溃），实现基于真实物理反馈的高阶自愈决策。
