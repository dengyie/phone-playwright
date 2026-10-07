# Phone-Playwright v2 进阶系统架构规格书 (System Architecture Specification)

## 1. 架构愿景与设计哲学

`phone-playwright` 旨在成为 AI-Native 时代最极致、最高性能、对 LLM/VLM Agent 最友好的全平台移动端自动化与多模态感知框架。

### 核心设计原则
1. **零外部强依赖与轻量启动 (Zero-Bloat Startup)**：框架核心保持纯 Python 实现，驱动层通过异步非阻塞 Subprocess 直接与底层 ADB / WDA 协议通信，启动开销 $< 20\text{ms}$。
2. **感知-动作闭环与温热缓存 (Perception-Action Warm Cache)**：快照（Snapshot）与动作（Action）共享 1.0s TTL 视口元素缓存，消灭传统框架多轮冗余 Dump 造成的性能黑洞。
3. **异构环境绝对鲁棒性 (Zero-Failure Heterogeneous Defense)**：面对物理机、云手机、模拟器、定制 ROM 等极端异构环境，设计完备的多通道自愈降级阶梯（如 Tri-Channel 输入体系）。
4. **LLM/VLM 双模感知原生支持 (Dual-Modal Native Perception)**：
   - 文本模态：提供最高信息密度、最省 Token 的 Markdown 语义清单。
   - 视觉模态：提供对齐编号的 Set-of-Mark (SoM) 标注图，赋予多模态大模型像素级精准交互能力。

---

## 2. 总体系统分层拓扑 (Layered Architecture Topology)

```
+-----------------------------------------------------------------------------+
|                      User & AI Agent Presentation Layer                     |
|  - Async/Sync Page API (Playwright-Compatible)                              |
|  - PhoneLocator & Expect Assertion Engine                                   |
|  - Set-of-Mark (SoM) Visual Renderer / Trace Viewer Recorder                |
+-----------------------------------------------------------------------------+
                                     | (Strict Unidirectional Call)
                                     v
+-----------------------------------------------------------------------------+
|                       Core Engine & State Machine                           |
|  - Actionability State Machine (Attached -> Visible -> Stable -> Enabled)   |
|  - Specificity-Scoring Selector Engine (@ref, exact:text, id, role)         |
|  - Viewport-Aware Semantic Pruner & Topological Ascendant Text Aggregator   |
|  - Gesture Engine (Bézier Smooth Trajectory, Multi-Touch Dispatcher)        |
+-----------------------------------------------------------------------------+
                                     | (Runtime Protocols & Interfaces)
                                     v
+-----------------------------------------------------------------------------+
|                      Multi-Channel Driver & Transport                       |
|  +---------------------------+  +-----------------------------------------+ |
|  |     Native Android ADB    |  |             iOS WDA Driver              | |
|  | - Tri-Channel Text Input  |  | - XCTest JSON-RPC Bridge                | |
|  | - Rotation-Aware Viewport |  | - Native Touch & Snapshot Engine        | |
|  | - Raw uiautomator Stream  |  +-----------------------------------------+ |
|  +---------------------------+                                              |
|  +------------------------------------------------------------------------+ |
|  |                    Hybrid CDP / DevTools Tunnel                        | |
|  | - Unix Socket Auto-Discovery (@devtools_remote_*)                       | |
|  | - Adb Forwarding & Chrome DevTools Protocol Frame Proxy                | |
|  +------------------------------------------------------------------------+ |
+-----------------------------------------------------------------------------+
                                     | (Physical I/O)
                                     v
+-----------------------------------------------------------------------------+
|            Physical Device / Cloud Phone / Emulator / iOS Runner            |
+-----------------------------------------------------------------------------+
```

---

## 3. 核心子系统与关键数据流

### 3.1 语义蒸馏与快照生成流 (Snapshot Pipeline)
1. **视口尺寸探查**：优先解析 `dumpsys window displays` 中的 `cur=WxH`（当前物理旋转空间），失败回退至 `wm size` 的 `Override size` / `Physical size`。
2. **原始多叉树 Dump**：通过 `uiautomator dump` 获取完整层级 XML，构建带虚拟根节点的 `RawNode` 多叉树（彻底保留跨窗口 Dialog 与浮层）。
3. **几何视口裁剪 (Geometric Viewport Clipping)**：以当前视口 $[0, 0, V_w, V_h]$ 为界，过滤完全脱离屏幕的无效节点。
4. **文本向上提升与角色推断 (Ascendant Text Aggregation & Role Inference)**：纯布局容器向上聚合叶子文本，推断语义角色（`button`, `input`, `scrollable` 等）。
5. **@ref 分配与温热预热**：为具备可交互属性（`clickable` / `editable` / `checkable`）的紧凑节点分配单调递增 `@1, @2...` 索引，并预热 `ActionabilityEngine` 的 1.0s TTL 缓存。

### 3.2 动作分发与状态机流 (Action Execution Pipeline)
```
[User / Agent Call] page.locator("text=确定").click()
         |
         v
[Selector Engine] 特异性评分解析 (Exact-Match > Leaf Smallest Area > List Order)
         |
         v
[Warm Cache Check] 是否存在 <= 1.0s 的元素缓存?
         +--- Yes ---> 直接复用物理边界 Rect(left, top, right, bottom)
         +--- No  ---> 动态重新 Dump + Distill 评估
         |
         v
[Actionability Auto-Waiting]
  1. Attached 断言 (DOM 存在)
  2. Visible 断言 (处于物理视口内；若不在视口但在虚拟空间则转入 Offscreen 诊断)
  3. Stable 断言 (连续采样间坐标波动 = 0)
  4. Enabled 断言 (组件未被 disable)
         |
         v
[Physical Dispatch]
  - tap: input tap cx cy
  - fill: input tap cx cy -> clear_text() -> Tri-Channel type_text() -> Post-Verification
  - swipe: input swipe sx sy ex ey duration_ms (或 Bézier 曲线插值)
```

---

## 4. 关键接口定义与领域模型契约

### 4.1 几何与选择器核心模型
```python
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict

class Rect(BaseModel):
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def center(self) -> tuple[int, int]:
        return (self.left + self.right) // 2, (self.top + self.bottom) // 2

class CompactElement(BaseModel):
    ref: Optional[str] = None
    role: Literal["button", "input", "item", "text", "image", "tab", "checkbox", "switch", "scrollable", "unknown"]
    text: str = ""
    bounds: Rect
    enabled: bool = True
    scrollable: bool = False
    resource_id: Optional[str] = None
```

---

## 5. 跨平台支持矩阵 (Support Matrix)

| 功能特性 | Android 物理真机 (Pixel/OnePlus) | Android 云手机 (Galaxy Fold/ARM64) | Android 模拟器 (MuMu/BlueStacks) | iOS 真机 / 模拟器 (WDA) |
|---|---|---|---|---|
| **视口自适应** | 物理旋转自动感知 (`dumpsys cur`) | Override 逻辑分辨率自动对齐 | 窗口拉伸/旋转自动对齐 | 逻辑 Points 自动映射 |
| **中文/Unicode输入** | 极速剪贴板广播通道 (`cmd clipboard`) | 自动回退 AdbIME 广播通道 | 宿主同步 / AdbIME 双通道 | WDA 原生 `type_text` 字符串注入 |
| **选择器特异性** | 精确等值优先 / 最小面积叶子择优 | 精确等值优先 / 最小面积叶子择优 | 精确等值优先 / 最小面积叶子择优 | 精确等值优先 / 最小面积叶子择优 |
| **SoM 视觉标注** | 原生无障碍树像素对齐标注 | 逻辑视口缩放对齐标注 | 宿主缩放自适应标注 | Retina 点阵倍率自适应标注 |
| **WebView CDP** | Unix 套接字直连穿透 | Unix 套接字直连穿透 | 端口转发直连穿透 | Safari Web Inspector 桥接 |
