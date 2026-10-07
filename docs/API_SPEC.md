# 面向 AI 的 API 契约与 MCP 协议规范

## 1. 客户端 SDK API 规范 (Playwright 风格)

SDK 提供直观、链式的调用方式，完全对标 Web 端 Playwright 习惯。

### 1.1 核心调用示例

```python
from phone_playwright import sync_phone_playwright

with sync_phone_playwright() as p:
    # 1. 发现并连接设备
    device = p.connect("192.168.1.3:43037") # 或 p.devices["oneplus-7t"]
    page = device.current_page()

    # 2. 获取 AI 友好的纯净快照
    snapshot = page.snapshot()
    print(snapshot.to_markdown()) 
    # 输出易读的 Markdown 清单给 LLM：
    # [@1] button: "搜索"
    # [@2] input: "输入商品名称"

    # 3. 语义化交互 (支持 Auto-waiting)
    page.locator("@2").fill("降噪耳机")
    page.locator("@1").click()

    # 4. 支持自然文本与语义定位
    page.get_by_text("综合排序").click()
    page.get_by_role("button", name="加入购物车").click()
```

### 1.2 API 接口详细签名

#### `PhonePage` 接口
| 方法名 | 参数 | 返回值 | 语义说明 |
| :--- | :--- | :--- | :--- |
| `snapshot()` | `include_screenshot: bool = False` | `PageSnapshot` | 抓取当前屏幕视口内的紧凑无障碍树 |
| `screenshot()` | `quality: int = 80` | `bytes` | 截取当前屏幕的 JPEG/PNG 二进制流 |
| `locator(selector)`| `str` | `PhoneLocator` | 创建一个延迟解析的定位器 |
| `get_by_text(text)` | `str, exact: bool = False` | `PhoneLocator` | 按文本内容定位 |
| `get_by_role(role, name=None)` | `str, str | None` | `PhoneLocator` | 按无障碍角色和标签定位 |
| `swipe(direction)` | `"up" \| "down" \| "left" \| "right"` | `None` | 执行标准视口滑动翻页 |
| `press_back()` | 无 | `None` | 模拟系统物理返回键 |
| `press_home()` | 无 | `None` | 返回手机系统桌面 |

#### `PhoneLocator` 接口
| 方法名 | 参数 | 返回值 | 语义说明 |
| :--- | :--- | :--- | :--- |
| `click()` | `timeout: float = 5.0` | `None` | 自动等待元素稳定可见后点击 |
| `fill(text)` | `text: str, timeout: float = 5.0`| `None` | 自动等待输入框可用，注入文本 |
| `hover()` | `timeout: float = 5.0` | `None` | 长按或悬浮触发特定菜单 |
| `wait_for()` | `state: "visible" \| "hidden", timeout: float` | `None` | 显式断言等待元素状态变更 |

---

## 2. Model Context Protocol (MCP) 服务端规范

为了让 ZCode、Claude Code、Cursor 等大模型宿主能够直接作为工具调用，本项目提供标准的 MCP Server 实现。

### 2.1 暴露的 MCP 工具列表

#### `phone_list_devices`
* **功能**：扫描局域网与 USB，列出当前可用的所有移动设备。
* **参数**：无。
* **返回值**：
  ```json
  [
    {
      "id": "192.168.1.3:43037",
      "model": "OnePlus 7T",
      "platform": "android",
      "state": "online"
    }
  ]
  ```

#### `phone_inspect_screen`
* **功能**：拉取指定设备的屏幕视口紧凑树，作为 AI 的“视觉神经”。
* **参数**：
  * `device_id` (string, 必填): 目标设备序列号或局域网地址。
  * `with_screenshot` (boolean, 可选, 默认 false): 是否附带截屏图片的 Base64 编码。
* **返回值**：
  ```json
  {
    "device": "192.168.1.3:43037",
    "screen_size": [1080, 2400],
    "app_current": "com.taobao.idlefish",
    "tree_summary": "当前在闲鱼搜索结果页，顶部有搜索栏，下方有商品瀑布流",
    "elements": [
      {"ref": "@1", "role": "button", "text": "返回"},
      {"ref": "@2", "role": "input", "text": "一加手机", "hint": "搜索"},
      {"ref": "@3", "role": "item", "text": "99新 一加7T 8+256G ￥650", "bounds": [50, 400, 500, 900]},
      {"ref": "@4", "role": "button", "text": "我想要", "bounds": [380, 850, 490, 890]}
    ]
  }
  ```

#### `phone_interact`
* **功能**：执行 Playwright 风格的动作，内置 Auto-waiting 状态机。
* **参数**：
  * `device_id` (string, 必填): 设备标识。
  * `action` (string, 必填): `click` | `fill` | `swipe` | `press_key`。
  * `target` (string, 可选): 目标的 `@ref` 编号（如 `"@4"`）或选择器（如 `"text=我想要"`）。
  * `value` (string, 可选): 当 action 为 `fill` 时输入的文本；或为 `swipe` 时传入 `"up" | "down"`。
* **返回值**：
  ```json
  {
    "status": "success",
    "action_executed": "click(@4)",
    "target_bounds": [380, 850, 490, 890],
    "waited_ms": 140
  }
  ```
