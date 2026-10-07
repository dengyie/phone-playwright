# Phone-Playwright 技术演进与架构设计规格书体系 (v2 Specifications)

本目录汇总了 `phone-playwright` 下一代移动端自动化与 AI-Native 多模态感知体系的完整工业级开发规格书。每一份规格均基于真实物理机（OnePlus 7T / Pixel）、定制云手机（三星 Galaxy Fold / ARM64）与主流模拟器（MuMu 12）的生产实战踩坑检验。

---

## 核心规格清单

| 规格编号 | 规格主题 | 核心关注点与突破 |
|---|---|---|
| [**DEVELOPER_GUIDE.md**](./DEVELOPER_GUIDE.md) | **核心深度开发指南与系统内核手册** | 工业级内核实现内幕、数学模型、避坑实录与端到端实机验证架构全集 |
| [**01-architecture-v2.md**](./specs/01-architecture-v2.md) | **总体分层拓扑与核心流** | 零强依赖单向依赖模型、快照温热缓存（1.0s TTL）、特异性评分选择器引擎、跨平台支持矩阵 |
| [**02-input-subsystem.md**](./specs/02-input-subsystem.md) | **Tri-Channel 三阶输入子系统** | 剪贴板广播 (Channel 1) $\to$ AdbIME Base64 广播 (Channel 2) $\to$ 严格转义 ASCII (Channel 3) 自愈阶梯；确定性批量退格替换清空语义 |
| [**03-vision-som-multimodal.md**](./specs/03-vision-som-multimodal.md) | **Set-of-Mark 视觉多模态标注** | 逻辑视口与物理点阵自适应归一化、高辨识度数字角标渲染、防遮挡避让算法、Token 紧凑压缩 |
| [**04-gesture-engine.md**](./specs/04-gesture-engine.md) | **高级手势与贝塞尔曲线轨迹** | 三阶贝塞尔曲线平滑插值、Sigmoid 变加速时钟模型、抗风控随机高斯抖动、`drag_to` / `pinch` 缩放 |
| [**05-cdp-hybrid-traversal.md**](./specs/05-cdp-hybrid-traversal.md) | **混合应用 (WebView) CDP 穿透** | Unix Domain Socket 自动发现 (`@*_devtools_remote_*`)、ADB 端口隧道映射、FrameLocator 混合定位 |
| [**06-expect-assertions-and-trace.md**](./specs/06-expect-assertions-and-trace.md) | **原生 Expect 断言与 Trace Viewer** | 单调时钟自旋重试状态机、Playwright 兼容 `trace.zip` 打包、逐帧动画与热点可视化回溯 |

---

## 实践原则与开发守则

1. **真实硬件第一**：所有核心驱动改动必须经过真实 Android/iOS 硬件验证，杜绝在纯 Mock 环境下的虚假繁荣。
2. **严禁静默假阳性**：失败必须显式阻断并给出具备可操作性的修复建议，严禁将中文乱码降级输入当作“执行成功”。
3. **零外部强包捆绑**：保持框架精简内核，视觉/CDP 等扩展能力采用按需懒加载机制（Lazy-Import / Duck-Typing）。
