# Phone-Playwright 系统架构设计与技术规范

Phone-Playwright 是一个专为 AI Agent 设计的跨平台（Android / iOS）移动端无障碍感知与确定性交互自动化框架。它将 Web 领域 Playwright 的核心设计哲学——**懒加载定位器（Lazy Locators）**、**可用性自动等待状态机（Actionability Auto-Waiting）** 与 **语义蒸馏（Semantic Pruning）** 深度结合并移植至移动操作系统，彻底解决移动端 UI 自动化中元素飘移、动画抖动、Token 消耗过大与多设备端口漂移等痛点。

---

## 1. 核心架构分层

Phone-Playwright 采用严格的分层解耦架构，自下而上分为五层：

```text
+-----------------------------------------------------------------------+
|  应用与服务层: Python Async/Sync SDK, MCP Server (STDIO), CLI / REPL    |
+-----------------------------------------------------------------------+
|  高层交互语义层: PhonePage, PhoneLocator, scroll_into_view, 快照引擎   |
+-----------------------------------------------------------------------+
|  可用性状态机层: ActionabilityEngine (Attached -> Visible -> Stable   |
|                 -> Enabled -> Dispatch), 1.0s 温热缓存加速             |
+-----------------------------------------------------------------------+
|  语义蒸馏与感知层: SemanticPruner (O(N) DFS, 几何裁剪, 语义提升),     |
|                   RapidOcrFallbackProvider (轻量视觉 OCR 兜底)        |
+-----------------------------------------------------------------------+
|  硬件桥接与集群层: AndroidAdbDriver, IosWdaDriver, FleetManager,     |
|                   Watchdog (mDNS 端口漂移感知与自动重连自愈)          |
+-----------------------------------------------------------------------+
```

---

## 2. 核心技术创新点

### 2.1 视口感知语义蒸馏算法 (Viewport-Aware Semantic Pruning)
在 Android 中，单次 `uiautomator dump` 输出的完整 XML 树往往超过数万字符，包含大量嵌套的 `FrameLayout`、`LinearLayout` 等纯布局容器，如果全量提交给大语言模型（LLM），不仅消耗高达数千 Token，还会引入严重的幻觉。

Phone-Playwright 实现了一遍深度优先遍历 ($O(N)$ DFS) 算法：
1. **几何相交裁剪**：计算每个节点与物理屏幕视口 `[0, 0, screen_w, screen_h]` 的重叠面积。过滤掉面积为 0 或完全处于视口外部的离屏节点。
2. **纯布局空容器折叠**：对于不可点击、无文本、无描述且不具备状态标识的中间容器节点，直接向上提升其子节点，消除无效 DOM 层级。
3. **语义标签向父提升**：对于复杂的交互卡片（如点击区域在外层容器，但文字与图标在深层嵌套节点），算法自动将所有后代有效语义信息（文字、内容描述）汇聚至最外层可交互父容器中，形成单一高内聚语义单元。
4. **确定性数字引用生成**：生成 `@1, @2, ...` 的紧凑数字索引，并在快照输出中渲染为超紧凑 Markdown 表格，使 LLM 的 Token 开销降低 **90% 以上**。

### 2.2 可用性自动等待状态机与快照温热缓存 (Actionability State Machine & Warm-Cache)
传统移动测试框架（如 Appium）常因在页面转场或动画未完成时下发点击而导致“静默丢失点击”（Flaky Tests）。Phone-Playwright 建立了严格的 5 阶段执行守卫：

1. **附加检查 (Attached)**：元素存在于当前的无障碍层级树中。
2. **视口可见 (Visible in Viewport)**：元素与屏幕有效视口相交，且可见面积大于阈值。
3. **几何稳定 (Stable)**：检测连续帧之间元素边界矩形的坐标抖动是否小于 $\epsilon$（在 Android 环境下，由于 UiAutomation dump 天然具备 waitForIdle 机制，单帧采样即可实现极速分发；针对动画屏幕支持多轮抖动采样）。
4. **使能检查 (Enabled)**：确认元素未被标记为 `enabled=false`。
5. **动作分发 (Dispatch)**：计算物理点击中心点坐标并执行底层驱动动作。

#### 1.0s 快照温热缓存机制
在 AI Agent 常见交互模式中，LLM 会先调用 `snapshot()` 审查当前屏幕，随后在数毫秒内对决策出的元素下发 `click()` 或 `fill()`。为避免在首击时重新触发一次耗时约 7 秒的冷启动 dump，引擎在 `snapshot()` 完成时保留 1.0s TTL 的温热缓存。紧随其后的首个动作直接复用该缓存进行边界计算与使能验证，将物理点击耗时从 **7640ms 极致压缩至 141ms（提升 54 倍）**！一旦发生物理交互（点击、滑动、按键），缓存立即失效清空，确保状态一致性。

### 2.3 无界虚拟视口诊断 (Unclipped Virtual Viewport Diagnostics)
当 locator 超时失败时，传统框架仅能抛出通用的 `TimeoutError`，AI 无法区分是“元素完全不存在”还是“元素因长列表滚动而处于当前可视区域之外”。
Phone-Playwright 引入无界虚拟视口（$1,000,000 \times 1,000,000$）进行超时事后诊断：
- 若元素在无界视口树中被命中：抛出 `OffscreenElementError`，并明确指出其所在物理绝对坐标，指导 Agent 调用 `.scroll_into_view()`。
- 若元素在无界视口树中仍未找到：抛出 `SelectorNotFoundError`，提示 Agent 检查拼写或切换选择器策略。

### 2.4 自动化 `scroll_into_view` 视口滚动引擎
对于处于深层长列表底部的元素（如“设置”界面的“关于本机”），`locator.scroll_into_view()` 引擎自动启动动态滑动与视口轮询循环：
- 逐次执行微距纵向滑动（默认向上划动半屏距离）；
- 每轮滑动后快速轻量探测无障碍树；
- 目标元素一旦几何进入当前物理视口，立即终止滑动并返回 locator，支持链式直接触发动作：
  ```python
  await page.get_by_text("关于本机").scroll_into_view().click()
  ```

### 2.5 集群看门狗与无线 ADB 端口漂移自愈 (Fleet Watchdog & Port Drift Healing)
针对 Wi-Fi ADB 环境下因网络抖动或系统休眠导致设备 IP 端口发生漂移（如 `192.168.1.3:43037` 漂移为 `192.168.1.3:39821`），Watchdog 结合 mDNS 服务发现（`_adb-tls-connect._tcp`）提供心跳探针。当物理连接超时断开时，看门狗在后台自动扫描 mDNS 服务广播，识别相同设备序列号并原子迁移驱动路由，使上层调用者完全无感。
