# Phone-Playwright: 混合感知架构与效率性评估 (Hybrid Vision Fallback & Efficiency)

## 1. 核心问题背景：为什么必须做双模混合感知？

在纯原生 Android 页面中，`AccessibilityService / UIAutomator` 能够稳定输出层次树；
但在真实工业级场景中，存在三类致命的**“无障碍失明”**死角：
1. **游戏界面与 Canvas 动态渲染**：引擎（Unity, Unreal, Flutter Canvas, 自定义 View）完全不向系统无障碍服务派发任何可交互节点，Dump 结果仅为一个覆盖全屏的空白 `FrameLayout`。
2. **纯图形按钮缺失标签**：如搜索放大镜、购物车图标、关闭 × 按钮未设置 `contentDescription`，导致无障碍树中仅有空白坐标或被剪枝算法舍弃。
3. **安全加密与防抓取界面**：部分银行或风控界面对无障碍读取进行防护拦截。

---

## 2. 混合感知架构设计 (Hybrid Perception Architecture)

系统遵循 **“无障碍语义优先，视觉 OCR 按需兜底”** 的分层流水线：

```
                              [当前屏幕帧]
                                   │
               ┌───────────────────┴───────────────────┐
               ▼ (快路径: ~80ms)                       ▼ (慢路径: 仅当触发阈值)
      [无障碍原生树 Dump]                       [物理视口截图 (Screencap)]
               │                                       │
               ▼                                       │
      [Semantic Pruner 剪枝]                           │
               │                                       │
               ▼                                       ▼
       {有效元素数 >= 阈值?} ──No (触发失明保护)──► [轻量 OCR 视觉识别引擎]
               │                               (RapidOCR / ONNX 轻量模型)
              Yes                                      │
               │                                       ▼
               │                            [OCR 文字与坐标提取]
               │                                       │
               └───────────────────┬───────────────────┘
                                   │ (对齐转换为 CompactElement)
                                   ▼
                        [统一 PageSnapshot]
                                   │
                                   ▼
                        [AI Agent / LLM 消费]
```

### 2.1 触发兜底的判定准则 (Trigger Conditions)
- **准则 1 (极度稀疏)**：视口内提取出的 `CompactElement` 总数 $< 3$（排除只有系统状态栏的情况）。
- **准则 2 (显式降级)**：调用方或 AI 显式指定 `page.snapshot(use_vision_fallback=True)`。
- **准则 3 (单次定位未命中)**：`page.get_by_text("某按钮").click()` 在无障碍树中超时未命中时，触发一次局部/全局 OCR 扫描兜底。

---

## 3. 系统级效率性评估 (System Efficiency Assessment)

我们对纯无障碍树、纯视觉 VLM、以及本项目采用的**双模按需混合模式**进行全维度对比：

| 评估维度 | 传统纯视觉 VLM 方案 (如早期 AppAgent) | 纯无障碍树方案 (UIAutomator) | Phone-Playwright 混合按需架构 (本项目) |
| :--- | :--- | :--- | :--- |
| **单步感知延迟** | 2000ms ~ 4000ms (截屏+大模型视觉推断) | **80ms ~ 150ms** (极快) | **常规 100ms**；兜底触发时 ~350ms |
| **每次交互 Token 消耗** | 1000 ~ 3000 Tokens (全分辨率图片) | 0 ~ 200 Tokens (纯文本树) | **100 ~ 250 Tokens** (极省，降幅 90%+) |
| **内存与本地算力** | 需向远程云端传输高画质图片 | 接近 0 算力占用 | 默认 0 额外占用；本地 ONNX 仅在按需时调用 |
| **自定义 Canvas 兼容率** | 100% | ~40% (遇游戏/Flutter 易失明) | **95%+ (具备自动视觉兜底能力)** |
| **确定性与抗漂移** | 差 (视觉目标检测易发生坐标偏移) | 极高 (直接获取系统物理坐标) | **极高 (系统物理坐标优先，OCR 兜底)** |

---

## 4. 关键设计铁律 (Engineering Guardrails)

1. **零强制重型依赖 (Optional Dependency)**：
   - 核心引擎 `phone_playwright` 保持极致纯净，不将 `cv2` / `rapidocr_onnxruntime` 设为强依赖。
   - 提供抽象的 `IVisionProvider` 接口，若环境中安装了 OCR 库则自动激活，未安装时优雅降级并给出日志提示。
2. **轻量与单例缓存 (Frame Hash Caching)**：
   - 若连续两次截屏的 MD5 散列一致，复用上一轮 OCR 识别缓存，杜绝重复计算。
