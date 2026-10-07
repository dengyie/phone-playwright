# Phone-Playwright API 完整参考手册

本手册详细列出 Phone-Playwright 提供的 Python 原生 API（异步与同步）、选择器规范与 MCP 协议工具接口。

---

## 1. 顶层入口类

### `AsyncPhonePlaywright` (异步环境)
```python
from phone_playwright.api.async_api import AsyncPhonePlaywright

async with AsyncPhonePlaywright() as pw:
    page = await pw.connect(device_id="192.168.1.3:43037")
    ...
```

### `SyncPhonePlaywright` (同步环境)
```python
from phone_playwright.api.sync_api import SyncPhonePlaywright

with SyncPhonePlaywright() as pw:
    page = pw.connect(device_id="192.168.1.3:43037")
    ...
```

---

## 2. Page API (`PhonePage` / `SyncPhonePage`)

| 方法 | 参数 | 返回值 | 说明 |
|---|---|---|---|
| `snapshot(include_screenshot=False)` | `include_screenshot: bool` | `PageSnapshot` | 获取当前屏幕紧凑语义快照，自动温热 1.0s 执行缓存。若参数为 True，回填 Base64 截图 |
| `locator(selector)` | `selector: str` | `PhoneLocator` | 构造惰性定位器对象 |
| `get_by_text(text, exact=False)` | `text: str, exact: bool` | `PhoneLocator` | 按显示文本或内容描述定位；多命中时按特异性择优（exact 精确等值优先；子串匹配取面积最小/最叶子者，避免命中聚合了全屏文本的祖先容器） |
| `get_by_role(role, name=None)` | `role: str, name: str \| None` | `PhoneLocator` | 按语义角色（Button, Input, CheckBox 等）定位 |
| `get_by_test_id(test_id)` | `test_id: str` | `PhoneLocator` | 按 Android resource-id 定位 |
| `swipe(direction, distance_ratio=0.5)` | `direction: Literal["up","down","left","right"], distance_ratio: float` | `None` | 执行全屏相对距离滑动手势，立即清空温热缓存 |
| `press_back()` | 无 | `None` | 触发系统返回键 (KEYCODE_BACK) |
| `press_home()` | 无 | `None` | 触发系统 Home 键 (KEYCODE_HOME) |
| `press_key(key_code)` | `key_code: int` | `None` | 触发指定 Android 键码 |
| `close()` | 无 | `None` | 断开连接并释放底层驱动资源 |

---

## 3. Locator API (`PhoneLocator` / `SyncPhoneLocator`)

| 方法 | 参数 | 返回值 | 说明 |
|---|---|---|---|
| `click(timeout_s=5.0)` | `timeout_s: float` | `ActionResult` | 自动等待元素 Attached -> Visible -> Stable -> Enabled 并执行中心点点击 |
| `fill(text, timeout_s=5.0)` | `text: str, timeout_s: float` | `ActionResult` | 自动定位输入框，通过广播剪贴板或 IME 输入文本（对中文字符与特殊字符天然安全） |
| `hover(timeout_s=5.0)` | `timeout_s: float` | `ActionResult` | 等待并悬停于元素上方（主要用于 iOS 或支持指针的平板） |
| `wait_for(state="visible", timeout_s=5.0)` | `state: Literal["visible", "hidden"], timeout_s: float` | `ActionResult` | 断言并等待元素变为可见或隐藏状态 |
| `scroll_into_view(max_swipes=5, direction="up", distance_ratio=0.5)` | `max_swipes: int, direction: str, distance_ratio: float` | `PhoneLocator` | 启动滑动搜寻循环，直到元素进入有效物理视口内 |
| `is_visible()` | 无 | `bool` | 瞬时检查元素在当前视口内是否可见（非阻塞） |
| `count()` | 无 | `int` | 统计当前视口内匹配该选择器的元素总数 |
| `text_content()` | 无 | `str \| None` | 获取首个匹配元素的文本内容或内容描述 |
| `bounding_box()` | 无 | `dict[str, int] \| None` | 获取首个匹配元素的绝对物理坐标 `{x, y, width, height}`；元素不在视口内时返回 `None` |

> **温热缓存复用**：`is_visible()` / `count()` / `text_content()` / `bounding_box()` 共享 `snapshot()` 预热的 1.0s TTL 温热缓存；同一秒内的连续读取不会重复触发 `dump_raw_tree` 物理扫描。一旦执行 `click` / `fill` / `swipe` 等物理动作，缓存立即失效。

---

## 3.1 Page 原始树导出

| 方法 | 适用对象 | 返回值 | 说明 |
|---|---|---|---|
| `dump_raw_tree()` | `AsyncPhonePage` / `SyncPhonePage` / `SyncPhoneDevice` | `RawNode` | 导出物理设备原始无障碍树层级（多叉树模型），用于深度调试与自定义蒸馏 |

---

## 3.2 滑动手势双模式 (`swipe`)

`AsyncPhonePage.swipe` 与 `SyncPhonePage.swipe` 同时支持两种调用形式：

```python
# 方向滑动（相对视口中心，默认距离比例 0.5）
await page.swipe(direction="up", distance_ratio=0.5)

# 绝对坐标滑动（物理像素，duration 单位为秒，内部自动换算毫秒）
await page.swipe(start_x=800, start_y=1200, end_x=200, end_y=1200, duration=0.3)
```

---

## 4. 选择器语法规范

Phone-Playwright 支持多种灵活且具备容错能力的选择器策略：

1. **紧凑数字索引引用 (`@index`)**：
   - 语法：`@1`, `@2`, `@15`
   - 映射：直接对应最新一次 `snapshot()` 返回列表中标记的元素索引。
2. **文本匹配 (`text=...`)**：
   - 语法：`text=设置`, `text=无线局域网`
   - 规则：模糊包含匹配；大小写敏感度低；同时匹配 `text` 与 `content-desc`。
3. **精准资源标识符 (`resource-id=...`)**：
   - 语法：`resource-id=com.android.settings:id/search_action_bar` 或简写 `id=...`。
4. **语义角色匹配 (`role=...`)**：
   - 语法：`role=Button`, `role=Input`, `role=CheckBox`。
5. **复合属性过滤**：
   - 语法：`role=Button[name='确定']`。

---

## 5. 异常体系与诊断分类

所有异常均继承自 `PhonePlaywrightError`，并携带 `message` 与 `suggestion`（修复建议）两个字段：

```text
PhonePlaywrightError
├── DeviceOfflineError          # 设备离线不可达、无线 ADB 连接失败或授权拒绝
├── ActionabilityTimeoutError   # 可用性状态机超时（元素存在但未能达到 Visible/Stable/Enabled 就绪态）
├── SelectorNotFoundError       # 选择器在整棵无障碍树（含无界视口诊断）中均未命中任何节点
└── OffscreenElementError       # 元素存在于 DOM 树中，但因长列表滚动处于当前物理视口之外
```

超时事后诊断顺序：状态机超时后引擎会以无界虚拟视口（1,000,000 × 1,000,000）重新蒸馏全树 —— 命中但在视口外抛 `OffscreenElementError`，完全未命中抛 `SelectorNotFoundError`，二者均不成立才抛通用 `ActionabilityTimeoutError`。

---

## 6. MCP Server STDIO 协议工具接口

运行 `python scripts/cli.py --device <id> mcp` 时，提供符合 MCP 规范（JSON-RPC 2.0）的标准 Tools，共 3 个：

- `phone_list_devices()`：扫描并列出局域网与 USB 当前所有在线可用的移动物理设备。
- `phone_inspect_screen(device_id, with_screenshot=False, use_vision_fallback=False)`：拉取当前屏幕的紧凑语义树、前台应用与 Markdown 元素表；可选附带截图 Base64。
- `phone_interact(device_id, action, target=None, value=None, timeout_s=5.0)`：执行具备 Auto-waiting 状态机的语义化动作。
  - `action` 枚举：`click` / `fill` / `hover` / `swipe` / `press_key` / `wait_for`
  - `target`：`@ref` 索引（如 `@1`）或语义选择器（如 `text=搜索`）
  - `value`：动作参数 —— `fill` 为填充文本；`swipe` 为方向 `up`/`down`/`left`/`right`；`press_key` 为键名 `back`/`home`/`enter` 或数字键码；`wait_for` 为 `visible`/`hidden`
