# Phone-Playwright 核心深度开发指南与系统内核技术手册
(Core Developer Guide & System Kernel Manual)

> **版本**：v2.0 Industrial Edition  
> **适用受众**：系统架构师、自动化框架核心开发者、AI 移动 Agent 工程师  
> **目标**：提供从硬件抽象、状态机、多叉树剪枝、自愈输入到多模态标注的端到端技术内幕、数学推导与生产实战规范。

---

## 目录

- [1. 架构总览与工程理念 (Core Philosophy & Architecture)](#1-架构总览与工程理念-core-philosophy--architecture)
  - [1.1 为什么需要 Phone-Playwright：对比传统移动自动化](#11-为什么需要-phone-playwright对比传统移动自动化)
  - [1.2 性能模型与 1.0s TTL 温热缓存加速](#12-性能模型与-10s-ttl-温热缓存加速)
  - [1.3 零外部强依赖与鸭子类型设计规范](#13-零外部强依赖与鸭子类型设计规范)
- [2. 系统拓扑与全链路执行时序 (End-to-End Execution Topology)](#2-系统拓扑与全链路执行时序-end-to-end-execution-topology)
  - [2.1 分层拓扑结构](#21-分层拓扑结构)
  - [2.2 核心执行时序流 (Snapshot -> Locator -> Action)](#22-核心执行时序流-snapshot---locator---action)
- [3. 视口感知语义蒸馏与剪枝内核 (Semantic Pruner Deep Dive)](#3-视口感知语义蒸馏与剪枝内核-semantic-pruner-deep-dive)
  - [3.1 $O(N)$ 深度优先几何裁剪算法](#31-on-深度优先几何裁剪算法)
  - [3.2 纯布局容器折叠与语义提升 (Semantic Hoisting)](#32-纯布局容器折叠与语义提升-semantic-hoisting)
  - [3.3 孙子节点防丢失保护 (Grandchildren Drop Defense)](#33-孙子节点防丢失保护-grandchildren-drop-defense)
  - [3.4 多窗口与系统弹窗并列树聚合技术](#34-多窗口与系统弹窗并列树聚合技术)
- [4. 选择器特异性计算与叶子消歧算法 (Selector Engine & Specificity Scoring)](#4-选择器特异性计算与叶子消歧算法-selector-engine--specificity-scoring)
  - [4.1 祖先容器贪婪聚合冲突根因剖析](#41-祖先容器贪婪聚合冲突根因剖析)
  - [4.2 特异性三级打分与叶子节点仲裁算法](#42-特异性三级打分与叶子节点仲裁算法)
  - [4.3 复合选择器语法规范](#43-复合选择器语法规范)
- [5. 可用性自动等待状态机 (Actionability Auto-Waiting State Machine)](#5-可用性自动等待状态机-actionability-auto-waiting-state-machine)
  - [5.1 五阶守护状态机 (Attached -> Visible -> Stable -> Enabled -> Dispatch)](#51-五阶守护状态机-attached---visible---stable---enabled---dispatch)
  - [5.2 视口几何求交中心点安全点击防出界机制](#52-视口几何求交中心点安全点击防出界机制)
  - [5.3 严格替换语义输入与确定性退格清空](#53-严格替换语义输入与确定性退格清空)
  - [5.4 事后无界虚拟视口分析与超时故障精准诊断](#54-事后无界虚拟视口分析与超时故障精准诊断)
- [6. Tri-Channel 三阶输入子系统自愈机制 (Tri-Channel Input Subsystem)](#6-tri-channel-三阶输入子系统自愈机制-tri-channel-input-subsystem)
  - [6.1 通道 1：系统剪贴板与原生 KEYCODE_PASTE (279) 广播](#61-通道-1系统剪贴板与原生-keycode_paste-279-广播)
  - [6.2 通道 2：AdbIME Base64 广播通道 (ADB_INPUT_B64) 与输入法自动恢复](#62-通道-2adbime-base64-广播通道-adb_input_b64-与输入法自动恢复)
  - [6.3 通道 3：严格字符级转义 ASCII 注入](#63-通道-3严格字符级转义-ascii-注入)
  - [6.4 终态检测与组合键重试机制](#64-终态检测与组合键重试机制)
- [7. 真实异构设备适配实战手册 (Real-Device & Cloud-Phone Recipes)](#7-真实异构设备适配实战手册-real-device--cloud-phone-recipes)
  - [7.1 三星 Galaxy Fold (Android 13 / EasyTier 组网) 踩坑实录](#71-三星-galaxy-fold-android-13--easytier-组网-踩坑实录)
  - [7.2 逻辑视口旋转感知：`cur=WxH` 与 `Override size` 优先级决策](#72-逻辑视口旋转感知curwxh-与-override-size-优先级决策)
  - [7.3 输入控件类名识别：AutoCompleteTextView 家族覆盖](#73-输入控件类名识别autocompletetextview-家族覆盖)
  - [7.4 MuMu 12 / 宿主剪贴板同步型模拟器实战配方](#74-mumu-12--宿主剪贴板同步型模拟器实战配方)
  - [7.5 Wi-Fi ADB 端口漂移与 mDNS 看门狗自愈机制](#75-wi-fi-adb-端口漂移与-mdns-看门狗自愈机制)
- [8. 拟人化手势与三阶贝塞尔曲线算法 (Human-Like Bézier Gesture Engine)](#8-拟人化手势与三阶贝塞尔曲线算法-human-like-bézier-gesture-engine)
  - [8.1 三阶贝塞尔曲线插值数学模型](#81-三阶贝塞尔曲线插值数学模型)
  - [8.2 Sigmoid 变加速时间扭曲函数](#82-sigmoid-变加速时间扭曲函数)
  - [8.3 元素拖拽 `drag_to` 与双指缩放 `pinch` 协议](#83-元素拖拽-drag_to-与双指缩放-pinch-协议)
- [9. Set-of-Mark (SoM) 视觉多模态标注渲染器 (Visual Multimodal Engine)](#9-set-of-mark-som-视觉多模态标注渲染器-visual-multimodal-engine)
  - [9.1 视口逻辑坐标与物理位图点阵归一化 (DPI Normalization)](#91-视口逻辑坐标与物理位图点阵归一化-dpi-normalization)
  - [9.2 语义调色板与高辨识度数字角标绘制](#92-语义调色板与高辨识度数字角标绘制)
  - [9.3 边界碰撞检测与防遮挡避让算法](#93-边界碰撞检测与防遮挡避让算法)
  - [9.4 面向 VLM 的多模态 Prompt 构造规范](#94-面向-vlm-的多模态-prompt-构造规范)
- [10. 混合应用 (WebView) CDP 穿透与 Trace 录制器 (Hybrid CDP & Tracing)](#10-混合应用-webview-cdp-穿透与-trace-录制器-hybrid-cdp--tracing)
  - [10.1 Chromium Unix Domain Socket 探测与端口转发](#101-chromium-unix-domain-socket-探测与端口转发)
  - [10.2 Playwright 兼容 Trace Viewer 录制规范](#102-playwright-兼容-trace-viewer-录制规范)
- [11. 开发者测试、类型守卫与贡献指南 (Testing & Contribution Guide)](#11-开发者测试类型守卫与贡献指南-testing--contribution-guide)
  - [11.1 Mypy 静态类型守卫要求](#111-mypy-静态类型守卫要求)
  - [11.2 Pytest 自动化测试矩阵与 Mock 驱动编写规范](#112-pytest-自动化测试矩阵与-mock-驱动编写规范)
  - [11.3 真实设备接入验证流程](#113-真实设备接入验证流程)

---

## 1. 架构总览与工程理念 (Core Philosophy & Architecture)

### 1.1 为什么需要 Phone-Playwright：对比传统移动自动化

传统移动测试框架（Appium、uiautomator2、Airtest、Facebook WDA Client）是为**人工预设脚本的静态测试**设计的，直接迁移至 **AI-Native 自主 Agent 决策闭环**时暴露出三大致命缺陷：

| 评估维度 | 传统框架 (Appium / uiautomator2) | Phone-Playwright (v2 Industrial) |
|---|---|---|
| **首击交互延迟** | $\approx 2.5\text{s} \sim 7.5\text{s}$（每次交互均需冷启动 Dump 并做多轮休眠采样） | **$\approx 140\text{ms}$**（快照 1.0s TTL 温热缓存直达，提速 50 倍以上） |
| **LLM 消费 Token** | 单页 $10\text{KB} \sim 80\text{KB}$ XML，单次消耗 $3000 \sim 15000$ Token，充满冗余布局容器 | 视口裁剪 + 语义提升后超紧凑 Markdown，**仅 $\approx 150 \sim 400$ Token（节省 95%）** |
| **元素定位确定性** | 祖先容器文字聚合导致点击屏幕正中心；转场未稳导致点击落空（Flaky） | **叶子特异性打分（Leaf Specificity）** + **五阶可用性状态机守卫** |
| **异构设备输入鲁棒性** | `input text` 遇空格截断、中文乱码；云手机剪贴板被屏蔽时静默空转假阳性 | **Tri-Channel 三阶输入自愈阶梯**（剪贴板 $\to$ AdbIME Base64 $\to$ ASCII 转义）+ 树检测核验 |
| **多模态 VLM 支持** | 仅支持截取原图，模型坐标幻觉严重（漂移率 $\ge 35\%$） | **Set-of-Mark (SoM) 动态角标**，直接映射 `[@1]` 序号，点击准确率 $\ge 98\%$ |

### 1.2 性能模型与 1.0s TTL 温热缓存加速

在 AI Agent 典型推理闭环中：
$$\text{Agent Loop}: \text{Observe (Snapshot)} \xrightarrow{\text{LLM 推理}} \text{Decide (Selector)} \xrightarrow{\text{Act (Click/Fill)}} \text{Next Step}$$

1. **冷启动 Dump 开销**：Android 系统的 `uiautomator dump` 为进程冷启动，在真实高配置物理机上物理耗时约 $1.8\text{s} \sim 2.2\text{s}$。
2. **温热缓存机制（Snapshot Warm-Cache）**：
   - 当调用 `page.snapshot()` 采集当前界面时，蒸馏得到的 `list[CompactElement]` 会被以 `time.monotonic()` 存入 `ActionabilityEngine._cached_elements`，设置 **TTL = 1.0s**。
   - LLM 完成推理后在 1.0s 内调用 `locator.click()` 或 `locator.fill()`，状态机直接**命中温热缓存**，跳过冗余的 `dump_raw_tree()`，仅做几何有效性校验即完成物理下发。
   - **交互后立即使效（Invalidate-on-Action）**：任何物理动作（点击、滑动、按键）下发成功的瞬间，缓存立即被重置为 `None`，防止跨界面读取陈旧脏数据。

### 1.3 零外部强依赖与鸭子类型设计规范

- **核心零强依赖**：框架核心仅依赖 Python 3.10+ 标准库与 `pydantic`（用于严格数据契约校验）。
- **解耦外部工具**：不强行依赖 `adbutils`、`appium-python-client` 等重量级三方包，驱动层通过异步无锁子进程管道（`asyncio.create_subprocess_exec`）直连系统的 `adb` 与 HTTP RESTful WDA。
- **扩展依赖按需懒加载 (Lazy-Import)**：
  - 端侧轻量视觉 OCR 仅在安装了 `rapidocr-onnxruntime` 时启用。
  - SoM 图像标注仅在安装了 `pillow` 时启用。

---

## 2. 系统拓扑与全链路执行时序 (End-to-End Execution Topology)

### 2.1 分层拓扑结构

```text
+-----------------------------------------------------------------------------------+
|                        应用接入层 (Application & Presentation)                     |
|   +-----------------------+   +----------------------+   +--------------------+   |
|   | Async SDK (Page/Loc)  |   | Sync SDK (Page/Loc)  |   | MCP Server (STDIO) |   |
|   +-----------------------+   +----------------------+   +--------------------+   |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
|                         高层交互门面 (High-Level Interaction)                       |
|   - PhoneLocator: 延迟解析、scroll_into_view、is_visible、bounding_box            |
|   - ExpectAssertions: expect(locator).to_be_visible() 轮询自旋断言               |
|   - TraceRecorder: Playwright 兼容 trace.zip 逐帧抓取与动作时序记录器             |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
|                         核心引擎层 (Core Engines & State Machine)                  |
|   +------------------------+   +----------------------+   +--------------------+  |
|   |  ActionabilityEngine   |   |   SemanticPruner     |   |   SelectorEngine   |  |
|   |  (五阶守卫状态机/温热缓存) |   | (O(N) 几何裁剪/提升) |   |  (特异性评分消歧)   |  |
|   +------------------------+   +----------------------+   +--------------------+  |
|   +------------------------+   +-----------------------------------------------+  |
|   |      GestureEngine     |   |               VisualSoMRenderer               |  |
|   | (三阶贝塞尔/Sigmoid加速) |   |        (DPI 坐标归一化/高对比度角标渲染)        |  |
|   +------------------------+   +-----------------------------------------------+  |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
|                       驱动与传输层 (Drivers & Hardware Transports)                 |
|   +------------------------+   +----------------------+   +--------------------+  |
|   |    AndroidAdbDriver    |   |     IosWdaDriver     |   |   CdpHybridTunnel  |  |
|   | (Tri-Channel/旋转视口) |   |  (RESTful XCTest API)|   | (Chromium Socket)  |  |
|   +------------------------+   +----------------------+   +--------------------+  |
|   +----------------------------------------------------------------------------+  |
|   |     FleetManager & DeviceWatchdog (mDNS 端口漂移感知 / 并发防重单例锁)       |  |
|   +----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
|                      物理硬件层 (Physical Android / iOS / Emulators)              |
+-----------------------------------------------------------------------------------+
```

### 2.2 核心执行时序流 (Snapshot -> Locator -> Action)

```text
User / AI Agent         PhonePage           ActionabilityEngine      SemanticPruner        AndroidAdbDriver
      |                     |                        |                     |                      |
      |--- 1. snapshot() -->|                        |                     |                      |
      |                     |--- dump_raw_tree() ------------------------------------------------>|
      |                     |<-- raw XML / hierarchy ---------------------------------------------|
      |                     |--- prune_and_distill() -------------------->|                       |
      |                     |<-- [CompactElement, ...] -------------------|                       |
      |                     |--- warm_cache(elements, t0) ->|                                     |
      |                     |--- get_current_app() ---------------------------------------------->|
      |<-- PageSnapshot ----|                                                                     |
      |                                                                                           |
      | (Agent 推理耗时 200ms)                                                                    |
      |                                                                                           |
      |--- 2. locator("text=搜索").click() --------->|                                             |
      |                     |                        |-- 命中 1.0s 温热缓存!                       |
      |                     |                        |-- 特异性评分匹配叶子节点                    |
      |                     |                        |-- 视口几何求交裁剪 (inter.center)           |
      |                     |                        |-- 使能状态检查 (enabled=True)               |
      |                     |                        |-- 清除温热缓存 (invalidate)                 |
      |                     |                        |--- tap(cx, cy) --------------------------->|
      |                     |                        |<-- tap complete ---------------------------|
      |<-- ActionResult(success=True, 140ms) --------|                                            |
```

---

## 3. 视口感知语义蒸馏与剪枝内核 (Semantic Pruner Deep Dive)

### 3.1 $O(N)$ 深度优先几何裁剪算法

Android 系统原始 XML 往往包含全屏的 DecorView、StatusBar、NavigationBar、空 FrameLayout。
`SemanticPruner.prune_and_distill` 算法在单次 DFS 遍历中完成过滤：
1. **视口几何碰撞检测**：
   ```python
   vp = Rect(left=0, top=0, right=viewport_width, bottom=viewport_height)
   inter = node.bounds.intersection(vp)
   if inter is None or inter.width < self.min_element_size or inter.height < self.min_element_size:
       return  # 整个子树完全处于视口外或物理尺寸 < 8px，直接剪枝
   ```
2. **交互性判定准则**：
   节点满足以下条件之一判定为交互节点：
   - `clickable == True` 或 `editable == True` 或 `checkable == True`
   - `scrollable == True` 且为无子节点的滚动叶子

### 3.2 纯布局容器折叠与语义提升 (Semantic Hoisting)

对于具有复杂卡片结构的界面：
```text
LinearLayout (clickable=True, bounds=[50,100][500,400])
  ├── ImageView (clickable=False)
  └── LinearLayout (clickable=False)
        ├── TextView (text="小米手环8")
        └── TextView (text="￥199")
```
- 传统提取方式会得到 2 个孤立的不可点击只读文本和 1 个空白的可点击容器，导致 AI 难以建立关联。
- **语义提升算法 (`_collect_descendant_texts`)**：
  在遇到可点击父容器时，算法向下递归最多 5 层子树，提取所有非空的 `text` 与 `desc`，去重后拼装为组合语义 `text="小米手环8 ￥199"`，生成单一紧凑元素 `[@1] item: "小米手环8 ￥199"`。

### 3.3 孙子节点防丢失保护 (Grandchildren Drop Defense)

在早期版本中，一旦父容器被判定为交互节点并生成了 `@ref`，若直接 `return` 停止遍历，会导致内部真正具备独立交互能力的孙子组件被静默丢弃（如可点击卡片右上角内嵌的“删除”按钮或“立即购买”按钮）。

**防丢守卫实现**：
```python
def _has_interactive_descendants(node: RawNode) -> bool:
    """递归检查当前节点下方是否存在任何可交互的子孙节点。"""
    for child in node.children:
        if child.clickable or child.editable or child.checkable:
            return True
        if _has_interactive_descendants(child):
            return True
    return False

# 仅当子孙树中完全没有任何独立交互控件时，才提前终止 DFS
if not _has_interactive_descendants(node):
    return
```

### 3.4 多窗口与系统弹窗并列树聚合技术

Android 系统中的权限授权框、下拉 Spinner 弹窗、Dialog 往往属于独立的 Window，UiAutomator dump 会产出包含并列顶级节点的 XML：
```xml
<hierarchy rotation="0">
  <android.widget.FrameLayout bounds="[0,0][1080,2400]"> ... </android.widget.FrameLayout>
  <android.widget.FrameLayout bounds="[50,500][1030,1200]"> ... </android.widget.FrameLayout>
</hierarchy>
```
`parse_android_xml_hierarchy` 创建虚拟根节点（Virtual Root Node），将所有 `<hierarchy>` 的直接子节点挂载为其子树，彻底避免多窗口转场时权限弹窗被截断丢失的隐患。

---

## 4. 选择器特异性计算与叶子消歧算法 (Selector Engine & Specificity Scoring)

### 4.1 祖先容器贪婪聚合冲突根因剖析

在 Android 很多桌面与列表场景（如三星桌面、系统设置页）：
- 根容器（如 `role=scrollable`）的全屏边界为 `[0, 0, 720, 1280]`，其文本由下属所有图标文本聚合而成：`"数字时钟 应用宝 图库 文件管理"`。
- 子按钮 `button: "应用宝"` 的物理边界为 `[172, 307, 328, 419]`。
- 若调用 `page.get_by_text("应用宝")`，由于根容器也是包含 `"应用宝"` 子串的节点且排在列表最前，若按常规遍历首个命中，会导致**点击屏幕绝对中心点 `(360, 640)`**，造成点击完全偏离目标应用图标！

### 4.2 特异性三级打分与叶子节点仲裁算法

在 `src/phone_playwright/core/selector.py` 中实现了**特异性打分器 (Specificity Scorer)**：

```python
def find_first(self, elements: list[CompactElement]) -> CompactElement | None:
    best: CompactElement | None = None
    best_score: float = float("inf")
    for el in elements:
        if not self.match(el):
            continue
        # 1. 显式精确匹配 exact:text=xxx：等值命中得分为 0.0，子串命中得分为 1.0
        if self.exact_text is not None:
            score = 0.0 if el.text == self.exact_text else 1.0
        # 2. 宽松子串匹配 text=xxx：面积最小（最叶子节点）得分最低（胜出）
        elif self.substring_text is not None:
            area = (el.bounds.right - el.bounds.left) * (el.bounds.bottom - el.bounds.top)
            score = 1.0 + float(area)
        # 3. @ref / id / role 选择器：保持原始声明与 DOM 顺序
        else:
            score = 2.0
            
        if score < best_score:
            best, best_score = el, score
    return best
```

### 4.3 复合选择器语法规范

| 选择器类型 | 语法示例 | 匹配规则与行为 |
|---|---|---|
| **紧凑数字引用** | `@1`, `@12` | $O(1)$ 精确命中对应 `ref` 的元素（最优先推荐） |
| **精确文本匹配** | `exact:text=应用宝` | 只有当元素提取文本完全等于目标串时才命中 |
| **子串文本匹配** | `text=应用宝`, `"应用宝"` | 包含该文本的元素集，面积最小的叶子节点胜出 |
| **测试 ID / 资源 ID**| `id=com.app:id/submit_btn` | 匹配 Android 原生 `resource-id` 属性 |
| **无障碍角色定位** | `role=button[name=确定]` | 匹配指定角色（button/input/switch 等）且含指定名称 |
| **纯角色定位** | `role=input` | 匹配当前视口内的首个输入框 |

---

## 5. 可用性自动等待状态机 (Actionability Auto-Waiting State Machine)

### 5.1 五阶守护状态机 (Attached -> Visible -> Stable -> Enabled -> Dispatch)

在超时窗口（默认 5.0 秒）内按轮询步长（默认 100ms）自旋检测：

1. **第 1 阶：Attached（挂载）**：目标节点必须存在于当前的紧凑元素树中；
2. **第 2 阶：Visible（可见）**：目标节点物理边界与视口矩形有非空交集，且交集宽、高均 $\ge 4\text{px}$；
3. **第 3 阶：Stable（静止）**：连续采样比对目标矩形坐标 `cur_bounds == last_bounds`。若元素因进场动画或惯性滑动发生位移，计数器重置继续等待；
4. **第 4 阶：Enabled（可用）**：针对交互类动作（`click`、`fill`、`hover`），断言目标 `enabled == True`；
5. **第 5 阶：Dispatch（物理下发）**：清除短生命周期缓存，下发底层硬件事件。

### 5.2 视口几何求交中心点安全点击防出界机制

**生产风险**：部分长卡片由于滚动仅部分露出（例如边界 `[0, 1200][720, 1600]`，而视口高度仅为 1280），如果直接取元素自身的几何中心点 $(360, 1400)$，会导致点击坐标落在屏幕外，被系统丢弃或误触底部导航栏。

**解法实现**：
```python
inter = target_el.bounds.intersection(viewport)
# 优先使用视口相交区域的中心点作为物理点击坐标
click_bounds = inter if inter is not None else target_el.bounds
cx, cy = click_bounds.center
```

### 5.3 严格替换语义输入与确定性退格清空

Web Playwright 的 `locator.fill(text)` 严格遵守**替换语义（Replace Value）**，而非追加（Append）。
针对移动端的清空实现：
- **不依赖 CTRL+A**：MuMu、部分定制云手机不支持 `keycombination 113 29`（CTRL+A），会把 CTRL 丢失导致单打一个字符 `A` 反向污染输入框。
- **确定性光标右移与连续退格**：
  ```python
  # MOVE_END (123) + 连续 100 次 DEL (67)
  keycodes = ["123"] + ["67"] * 100
  await self._run_adb("shell", "input", "keyevent", *keycodes)
  ```
  在空字段上 DEL 为无操作，单次批量下发耗时仅 $\approx 130\text{ms}$，极度稳定可靠。

### 5.4 事后无界虚拟视口分析与超时故障精准诊断

当 5 秒超时耗尽时，传统框架直接抛出无上下文的 `TimeoutError`。
Phone-Playwright 在抛出前启动**无界虚拟视口（$1,000,000 \times 1,000,000$）事后诊断**：
- 若在全量树中找到了该元素：抛出 `OffscreenElementError`，明确提示元素处于屏幕下方绝对坐标，引导 AI 调用 `.scroll_into_view()`；
- 若全量树中依然没有该元素：抛出 `SelectorNotFoundError`，提示选择器不存在。

---

## 6. Tri-Channel 三阶输入子系统自愈机制 (Tri-Channel Input Subsystem)

### 6.1 通道 1：系统剪贴板与原生 KEYCODE_PASTE (279) 广播

- **命令实现**：`cmd clipboard set text <quoted_text>` + `input keyevent 279`
- **支持场景**：原生 Android 8.0+ 物理机（Pixel、OnePlus、小米等）。
- **屏蔽检测**：云手机和模拟器常屏蔽 shell 剪贴板，返回 rc=0 但 stderr 含 `"No shell command implementation."`。框架匹配该 marker 自动标记通道 1 失效。

### 6.2 通道 2：AdbIME Base64 广播通道 (ADB_INPUT_B64) 与输入法自动恢复

- **命令实现**：
  ```bash
  am broadcast -a ADB_INPUT_B64 --es msg <base64_encoded_utf8_text>
  ```
- **核心价值**：
  - 绕过 ROM 层所有剪贴板安全限制；
  - 零延迟、不弹软键盘输入窗；
  - 完美支持长文本、换行符、Emoji、多国语言。
- **输入法自动恢复生命周期**：
  - 在首次使用时，记录系统当前默认输入法：
    `settings get secure default_input_method -> com.samsung.android.honeyboard/.service.HoneyBoardService`
  - 自动启用并激活 `com.android.adbkeyboard/.AdbIME`；
  - 在驱动关闭（`disconnect()`）或会话退出时，**自动还原原始输入法**，对用户无侵入。

### 6.3 通道 3：严格字符级转义 ASCII 注入

针对无中文的纯 ASCII 字符串（如 URL、密码、数字），采用安全转义走高速通道：
- 空格映射为 `%s`；
- Shell 元字符 (`'"`、`&`、`$`、`\`、`|`、`*` 等）逐字符添加反斜杠转义；
- 下发 `input text <escaped_str>`。

### 6.4 终态检测与组合键重试机制

为防范任何“假阳性”成功：
1. 文本注入后等待 300ms；
2. 在当前无障碍树中进行文本遍历核验（`_tree_contains_text`）；
3. 若未检测到目标文本且剪贴板通道正常，补发一次 `Ctrl+V`（`input keycombination 113 47`）组合键重试；
4. 若多通道尝试后仍未检测到文本，立即显式抛出 `PhonePlaywrightError` 并附带明确排查指南，**绝不进行静默乱码降级**。

---

## 7. 真实异构设备适配实战手册 (Real-Device & Cloud-Phone Recipes)

### 7.1 三星 Galaxy Fold (Android 13 / EasyTier 组网) 踩坑实录

在通过 EasyTier 局域网组网直连的三星 Galaxy Fold 云手机 (`10.144.144.51:5555`) 上的真实踩坑：

| 现场问题现象 | 根因剖析 | 最终工程解法 |
|---|---|---|
| `app_process` 执行 Dalvik 报错 `Operation not permitted (core dumped)` | Android 13 对 shell 用户写入 `/data/local/tmp/dalvik-cache` 施加了严格 SELinux 沙箱限制 | 放弃在 shell 下自行 bootstrap Java 单文件，转向预装的 `com.android.adbkeyboard/.AdbIME` 广播 |
| `cmd clipboard set text` 注入无效 | 云手机服务商在 ROM 侧裁剪了剪贴板 shell 实现，返回 rc=0 但 stderr 含提示 | 自动识别 `_CLIPBOARD_UNSUPPORTED_MARKERS`，平滑直降到 AdbIME 广播通道 |
| 点击设置搜索框，`role=input` 报元素未找到 | 三星 OneUI 搜索控件是 `android.widget.AutoCompleteTextView`，类名不含 `edit` | 扩展 `_is_editable_class` 覆盖 `autocompletetextview` 与 `searchautocomplete` |
| 横折叠屏展开态下，手势与剪枝坐标严重旋转错位 | `wm size` 第一行返回未旋转的 `Physical size: 1080x1920`，而展开逻辑分辨率为 `1280x720` | 优先读取 `dumpsys window displays` 的 `cur=WxH`，fallback 优先匹配 `Override size:` |

### 7.2 逻辑视口旋转感知：`cur=WxH` 与 `Override size` 优先级决策

```python
# 1. 优先读取当前旋转下的真实应用空间尺寸 (cur=WxH)
display_info = await self._run_adb("shell", "dumpsys", "window", "displays")
match = re.search(r"cur=(\d+)x(\d+)", display_info)
if match:
    return int(match.group(1)), int(match.group(2))

# 2. wm size 降级方案：必须优先匹配 Override size (逻辑分辨率)
output = await self._run_adb("shell", "wm", "size")
override = re.search(r"Override size:\s*(\d+)x(\d+)", output)
physical = re.search(r"Physical size:\s*(\d+)x(\d+)", output)
match = override or physical
```

### 7.3 输入控件类名识别：AutoCompleteTextView 家族覆盖

```python
_EDITABLE_CLASS_MARKERS = (
    "edittext",
    "autocompletetextview",
    "searchautocomplete",
    "textfield",
)
```

### 7.4 MuMu 12 / 宿主剪贴板同步型模拟器实战配方

MuMu 12 会自动将宿主（Windows）剪贴板双向同步至安卓系统：
- 在 Windows 宿主预先写入剪贴板（如通过 `win32clipboard`）；
- 驱动虽然在设备端收到 `cmd clipboard` 不支持，但会尝试粘贴并经终态树校验成功命中宿主同步内容，实现稳定无缝注入。

### 7.5 Wi-Fi ADB 端口漂移与 mDNS 看门狗自愈机制

- **现象**：Android 11+ 的无线调试在网络重连或重启后，端口会在 $30000 \sim 45000$ 之间随机漂移。
- **自愈机制**：
  `DeviceWatchdog` 以 10 秒为周期执行心跳探活。当探测失败时，调用 `MdnsDiscovery` 查询 `_adb-tls-connect._tcp` 局域网广播，获取相同 IP 下注册的新端口，原子更新 `FleetManager._drivers` 字典并执行 `adb connect <new_ip:new_port>`，上层正在执行的 Playwright 任务无感恢复。

---

## 8. 拟人化手势与三阶贝塞尔曲线算法 (Human-Like Bézier Gesture Engine)

### 8.1 三阶贝塞尔曲线插值数学模型

设起点为 $P_0(x_0, y_0)$，终点为 $P_3(x_3, y_3)$。中间控制点引入正交法向量方向的高斯扰动 $\delta \sim \mathcal{N}(0, \sigma^2)$（其中 $\sigma = 0.08 \times \text{距离}$）：

$$B(t) = (1-t)^3 P_0 + 3(1-t)^2 t P_1 + 3(1-t) t^2 P_2 + t^3 P_3, \quad t \in [0, 1]$$

```python
def generate_bezier_trajectory(
    start: tuple[int, int], end: tuple[int, int], steps: int = 25
) -> list[tuple[int, int]]:
    p0 = np.array(start, dtype=float)
    p3 = np.array(end, dtype=float)
    dist = np.linalg.norm(p3 - p0)
    normal = np.array([-(p3[1] - p0[1]), p3[0] - p0[0]]) / (dist + 1e-6)
    
    # 随机生成两个控制点
    p1 = p0 + (p3 - p0) / 3.0 + normal * np.random.normal(0, dist * 0.08)
    p2 = p0 + (p3 - p0) * 2.0 / 3.0 + normal * np.random.normal(0, dist * 0.08)
    
    points: list[tuple[int, int]] = []
    for i in range(steps + 1):
        t = i / steps
        pt = (1 - t)**3 * p0 + 3 * (1 - t)**2 * t * p1 + 3 * (1 - t) * t**2 * p2 + t**3 * p3
        points.append((int(round(pt[0])), int(round(pt[1]))))
    return points
```

### 8.2 Sigmoid 变加速时间扭曲函数

模拟人类手指“慢速启动 $\to$ 快速滑动 $\to$ 减速对齐”的物理特征：
$$s(\tau) = \frac{1}{1 + e^{-k(\tau - 0.5)}}, \quad \tau \in [0, 1]$$
使得生成的轨迹点两端稠密、中间稀疏，有效规避风控算法对线性机械滑动的检测。

### 8.3 元素拖拽 `drag_to` 与双指缩放 `pinch` 协议

- **`locator.drag_to(target_locator)`**：
  1. 自动等待两者 Visible & Stable；
  2. 在起点长按 300ms 触发原生拖拽手柄；
  3. 沿贝塞尔多步轨迹滑动至终点；
  4. 终点停顿 80ms 释放。
- **`page.pinch_in()` / `page.pinch_out()`**：
  通过双指对角线向内/向外同步差分轨迹，用于地图和图片的缩放交互。

---

## 9. Set-of-Mark (SoM) 视觉多模态标注渲染器 (Visual Multimodal Engine)

### 9.1 视口逻辑坐标与物理位图点阵归一化 (DPI Normalization)

由于系统无障碍视口分辨率与实际截屏位图可能存在 DPI 缩放差异：
$$S_x = \frac{W_{\text{image}}}{W_{\text{viewport}}}, \quad S_y = \frac{H_{\text{image}}}{H_{\text{viewport}}}$$
在绘制矩形框与角标前，所有坐标统一经仿射缩放变换转换至像素点阵。

### 9.2 语义调色板与高辨识度数字角标绘制

根据元素语义角色分配色彩，强化 VLM 对控件类型感知：
- **`button`**：鲜明亮绿 (`#00C853`)
- **`input`**：高对比琥珀黄 (`#FFAB00`)
- **`item` / `tab`**：紫罗兰 (`#6200EA`)
- **角标绘制**：在元素左上角外缘绘制带 3px 圆角的矩形 Badge，内嵌白色加粗文字（如 `[@1]`），确保即使在复杂背景图上也具备极高辨识度。

### 9.3 边界碰撞检测与防遮挡避让算法

当多个元素紧密并列（如宫格图标）时，如果左上角角标发生重叠：
- 算法计算相邻角标的 Bounding Box 重叠率；
- 当重叠率 $> 20\%$ 时，次级角标自动避让至元素右上角或右下角；
- 紧贴屏幕顶部边缘的角标自动内收，防止被截断。

### 9.4 面向 VLM 的多模态 Prompt 构造规范

`snapshot.to_multimodal_prompt()` 输出标准 Payload：
```python
{
    "image_base64": "<SoM 标注图 Base64 编码>",
    "markdown_tree": """
# Device Viewport: 720x1280
# Active App: com.android.settings
## Interactive Elements:
- [@1] button: "搜索设置"
- [@2] item: "WLAN 已连接"
- [@3] item: "蓝牙 已开启"
"""
}
```
VLM 只需理解画面上的 `[@1]` 标号并回复操作指令，彻底解决纯文字失明与纯视觉坐标幻觉。

---

## 10. 混合应用 (WebView) CDP 穿透与 Trace 录制器 (Hybrid CDP & Tracing)

### 10.1 Chromium Unix Domain Socket 探测与端口转发

在 Android 混合应用（WebView / 微信小程序 / 百度 App）中：
1. **套接字探测**：
   ```bash
   cat /proc/net/unix | grep -E "devtools_remote|chrome_devtools_remote"
   # 输出: 0000000000000000: ... @webview_devtools_remote_14232
   ```
2. **端口隧道建立**：
   ```bash
   adb forward tcp:9222 localabstract:webview_devtools_remote_14232
   ```
3. **CDP 挂载**：
   通过 WebSocket 连接 `ws://localhost:9222/devtools/page/...`，复用 Chrome DevTools Protocol 直接读取 DOM 树并执行 JS 注入。

### 10.2 Playwright 兼容 Trace Viewer 录制规范

框架支持生成符合官方规范的 `trace.zip`：
```text
trace.zip
├── manifest.json         # 包含设备信息、视口、开始/结束时间、动作总数
├── trace.trace           # JSONL 格式的动作时序记录 (TraceActionRecord)
└── resources/
    ├── snapshot_001.png  # 动作前快照
    ├── snapshot_002.png  # 动作后快照
    └── ...
```
可直接拖入官方 [trace.playwright.dev](https://trace.playwright.dev/) 进行单步动作复盘。

---

## 11. 开发者测试、类型守卫与贡献指南 (Testing & Contribution Guide)

### 11.1 Mypy 静态类型守卫要求

项目开启严格的 Python 3.12+ 类型标注规范。提交代码前必须确保静态类型检查 0 错误：
```bash
mypy src tests
# 必须输出: Success: no issues found in XX source files
```

### 11.2 Pytest 自动化测试矩阵与 Mock 驱动编写规范

测试位于 `tests/` 目录下，包含 42 项以上自动化单元测试：
- **`DummyDriver` 规范**：实现 `BaseDriver` 抽象，记录 `tapped_coords`、`typed_texts`、`dump_raw_tree` 供断言验证；
- **运行全量测试**：
  ```bash
  pytest
  ```

### 11.3 真实设备接入验证流程

在推向生产环境前，执行端到端真实设备验证：
```bash
python -c "
import asyncio
from phone_playwright import async_phone_playwright

async def main():
    async with async_phone_playwright() as pw:
        device = await pw.connect('10.144.144.51:5555')
        page = device.current_page
        snap = await page.snapshot()
        print('成功连接设备并蒸馏元素:', len(snap.elements))

asyncio.run(main())
"
```
确保全链路正常返回，无异常抛出。
