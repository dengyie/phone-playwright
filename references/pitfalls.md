# Phone-Playwright 生产实战踩坑与避坑手册

本手册汇总了在真实硬件（如 OnePlus 7T / ColorOS、小米 MIUI、三星 Galaxy Fold 云手机、MuMu 模拟器与原生 Android 13/14）与网络化 ADB 部署中踩过的全部硬核生产问题与根因解法。

---

## 1. 性能与延迟问题

### 1.1 `uiautomator dump` 单次耗时 7 秒导致点击卡顿
- **真实表现**：调用 `click()` 时，虽然元素在界面上早已展示，但点击动作迟迟下发不了，日志显示耗时高达 7.6 秒。
- **根本原因**：
  1. Android 系统的 `uiautomator dump` 命令属于冷启动进程，需要在底层启动 Java 运行时并枚举整棵 AccessibilityNodeInfo 树。
  2. 传统框架在收到 `click("text=xxx")` 指令后，会盲目重新触发一次 dump。
  3. 如果设置多轮连续稳定度采样（如 `stable_sample_count=2`），连续两次 dump 就会消耗 $2 \times 3.8s = 7.6s$。
- **根因解法**：
  - **快照温热缓存（Snapshot Warm-Cache）**：在 AI 交互模式下，LLM 刚通过 `snapshot()` 审查过界面（该过程刚生成了有效元素树）。引擎为该树保留 1.0s TTL。后续动作若在 1.0s 内发生，直接跳过 dump 与采样，直接复用已校验边界执行点击。耗时从 **7640ms 降至 141ms**。
  - **默认单采样极速分发**：UiAutomation 在原生层 dump 时内部已经执行了 `waitForIdle`。因此除非是持续位移动画，默认单采样 `stable_sample_count=1` 即可保证点击命中率。

---

## 2. Windows 平台管道与多线程兼容性

### 2.1 Windows IOCP `[WinError 6] 句柄无效`
- **真实表现**：在 Windows 上运行 MCP Server 时，进程在启动或接收第 2 条输入时直接崩溃：`OSError: [WinError 6] 句柄无效`。
- **根本原因**：
  - Windows 平台的 Python `asyncio` 默认使用 `ProactorEventLoop`（基于 IOCP）。
  - `loop.connect_read_pipe` 对 Windows 标准输入（STDIO/Console Handle）的支持存在已知缺陷，当标准输入不是具名匿名管道或由特定父进程重定向时，IOCP 绑定抛出 WinError 6。
- **根因解法**：
  - 在 `mcp/server.py` 中，采用 `await loop.run_in_executor(None, sys.stdin.readline)` 跨平台线程池读取，完全免疫 Windows IOCP 句柄失效问题，并实现优雅无锁通信。

---

## 3. 输入法与中文特殊字符乱码

### 3.1 `adb shell input text` 丢失空格与特殊字符，中文直接报错
- **真实表现**：尝试输入含有空格、引号或中文的内容时，ADB 返回 `Killed` 或界面只输入了前半段，中文全部变为空白。
- **根本原因**：
  - `input text` 仅仅是将字符映射为底层 Linux Key Event。它不仅无法处理非 ASCII 编码的 Unicode 中文字符，且命令行中的 `&`, `|`, `'`, `"`, ` ` 会被 Shell 解释器直接转义或截断。
- **根因解法**：
  - Phone-Playwright 在 AndroidDriver 中实现了带终态校验的安全输入通道：
    1. **非 ASCII 文本（唯一通道，硬失败策略）**：通过 `cmd clipboard set text` 广播写入系统剪贴板，再下发粘贴键码（`KEYCODE_PASTE = 279`）。对中英文、Emoji 及任意特殊字符 100% 免疫。
    2. **注入终态校验**：粘贴后主动在无障碍树中检索目标文本。部分 ROM/模拟器（如 MuMu）对 `cmd clipboard` 返回 rc=0 + "No shell command implementation."（静默空转），或粘贴键码未被应用——此时若通道仍可用会补发一次 `Ctrl+V` 组合键重试，仍失败则显式抛出 `PhonePlaywrightError` 并附带修复建议，**绝不静默降级到 `input text`**（那会把中文注入成乱码/丢字，造成"输入成功但内容错误"的假阳性）。
    3. **纯 ASCII 文本（严格转义）**：对空格（→ `%s`）与全部 Shell 元字符逐字符反斜杠转义后走 `input text`。
- **排查指引**：
  - 收到"剪贴板写入失败"/"未在界面树中检测到输入文本"错误时，说明该 ROM 不支持 shell 端剪贴板广播，可安装 ADBKeyBoard 输入法作为替代注入通道。
  - **三星云手机实测**：三星 Galaxy Fold 云手机（Android 13，EasyTier 组网）同样对 `cmd clipboard set text` 返回 `rc=0 + "No shell command implementation."`，云服务商在 ROM 侧关闭了 shell 剪贴板。框架按设计命中该标记、尝试粘贴→树校验 → 补发 Ctrl+V → 仍失败则抛出带建议的 `PhonePlaywrightError`，不做静默降级。
  - **MuMu/云手机专用配方**：MuMu 12 会将宿主 (Windows) 剪贴板同步至安卓侧。先在宿主写入相同文本（如 `win32clipboard.SetClipboardText(text, CF_UNICODETEXT)`），再调用 `fill()` —— 框架检测到 `cmd clipboard` 通道未实现后仍会执行粘贴，宿主同步内容即可命中终态校验。

---

## 4. 视口与长列表滚动异常

### 4.1 元素在页面底部但 locator 报未找到，无法触发滚动
- **真实表现**：页面底部存在“关于本机”选项，代码直接调用 `page.get_by_text("关于本机").click()` 报超时失败，且报错提示未找到该元素。
- **根本原因**：
  - 许多移动系统（如 ColorOS/MIUI）的列表组件具有懒渲染或由于处于当前屏幕物理视口外部，在视口几何裁剪中被过滤。
  - 传统框架粗暴报错，调用者不知道元素是因为在可视范围外还是不存在。
- **根因解法**：
  - **无界虚拟视口事后分析**：超时发生后，引擎使用 $1,000,000 \times 1,000,000$ 的无界视口重新评估。若在 DOM 树中命中但在物理视口外，精确抛出 `OffscreenElementError`。
  - **链式滚动**：支持 `await page.get_by_text("关于本机").scroll_into_view().click()`，动态滚动并自动对准视口。

### 4.2 模拟器/云手机横屏时坐标与滑动几何错位 90°
- **真实表现**：MuMu 等模拟器/云手机运行横屏应用（如浏览器）时，`wm size` 仍返回竖屏物理面板尺寸（`Physical size: 900x1600`），而元素树坐标处于当前旋转空间（1600x900）。方向滑动 `swipe(direction="up")` 的坐标越界（y > 900），语义蒸馏的视口裁剪也随之失真。
- **根因解法**：
  - `get_viewport_size()` 优先解析 `dumpsys window displays` 的 `cur=WxH`（当前旋转下的真实应用空间尺寸），不可用时回退 `wm size`；缓存带 1.0s TTL，旋转后自动刷新。滑动几何、蒸馏裁剪与无界视口诊断共用同一坐标系。

### 4.3 三星云手机 `wm size` 返回 Physical 而非 Override，回退取值错尺寸
- **真实表现**：三星 Galaxy Fold 云手机（Android 13）被云服务商强制逻辑分辨率 `Override size: 1280x720`（横屏），但 `wm size` 输出为两行：
  ```
  Physical size: 1080x1920
  Override size: 1280x720
  ```
  旧回退逻辑 `re.search(r"(\d+)x(\d+)", output)` 取**首个**匹配即首行物理尺寸 1080x1920，与元素树实际坐标系（1280x720）不符，横屏下 distill 裁剪与 swipe 几何全部错位。
- **根因解法**：
  - 回退解析按关键字匹配：优先 `Override size:\s*(\d+)x(\d+)`，无则 `Physical size:\s*(\d+)x(\d+)`，二者顺序无关，避免被首行的物理尺寸劫持。

---

## 5. 定位器精度与控件识别

### 5.1 `get_by_text` 贪婪命中全屏祖先容器，点击落在屏幕中心
- **真实表现**：`page.get_by_text("应用宝").click()` 返回 `success=True`，但应用根本没有被打开；`bounding_box()` 返回整个视口 `{x:0, y:0, w:1280, h:720}`。屏幕上"应用宝"图标明明在底部。
- **根本原因**：
  - 语义蒸馏会把子节点文本**向上聚合**到祖先容器。桌面根 `scrollable` 节点的聚合文本包含了整屏所有图标名，因此 `text=应用宝`（子串匹配）同时命中：根 scrollable（全屏）、item（全屏）、button（真实图标）三个元素。
  - 旧 `Selector.find_first` 按列表顺序返回**第一个**命中者 —— 恰是排在最前的全屏根容器，于是 tap 坐标落在屏幕中心空白处，"命令成功但功能未发生"。
- **根因解法**：
  - `Selector.find_first` 改为**特异性评分**择优：
    1. `exact:text=` 选择器：精确等值文本（score 0）优先于子串命中（score 1）；
    2. `text=`/默认子串选择器：命中集合中取**面积最小**（最叶子/最具体）者，`score = 1 + 元素面积`；
    3. `@ref` / `id=` / `role=` 等无文本偏向的选择器保持原始列表顺序（score 2，并列取首个）。
  - 修复后 `bounding_box()` 返回真实图标边界 `{x:172, y:307, w:156, h:112}`，click 真正拉起目标应用。

### 5.2 `editable` 漏判 `AutoCompleteTextView`，搜索框无法被 fill 定位
- **真实表现**：三星 Settings 顶部搜索框（真实输入控件为 `android.widget.AutoCompleteTextView`）在树里 `editable=False`，`role=input` 推断失效，`fill()` 无法定位该字段。
- **根本原因**：
  - 旧判定为 `focusable=true AND "edit" in class.lower()`，而 `AutoCompleteTextView` / `MultiAutoCompleteTextView` / `SearchAutoComplete` 类名**不含 "edit" 子串**，被整体漏判。
- **根因解法**：
  - 抽出 `_is_editable_class()`，按可编辑控件类标记集匹配：`("edittext", "autocompletetextview", "searchautocomplete")`。覆盖 `EditText` / `AppCompatEditText` / `TextInputEditText` / `AutoCompleteTextView` / `MultiAutoCompleteTextView` / `SearchAutoComplete` 全家族，`role=input` 随之正确推断。

---

## 6. 无线 Wi-Fi ADB 与连接漂移

### 6.1 手机锁屏或 DHCP 续租导致 ADB 端口改变
- **真实表现**：连接 `192.168.1.3:43037` 几分钟后，设备离线并报 `Connection refused`，而手机端设置里端口已经变成了 `192.168.1.3:39821`。
- **根本原因**：
  - Android 11+ 无线调试每次重启服务或网络重连都会随机分配高位端口。
- **根因解法**：
  - 集群管理器配备 `FleetWatchdog`，结合局域网 mDNS（广播服务 `_adb-tls-connect._tcp`）探测广播包。一旦心跳丢失，自动提取新端口并在驱动内部完成原子路由切换，保证上层自动化脚本无需硬编码重启。
