# Phone-Playwright 📱🎭

> **Playwright for Mobile**：面向大模型与自主 Agent 的移动端语义感知与确定性交互自动化框架。

---

## 🌟 核心特性

1. **视口感知树剪枝与蒸馏 (Viewport-Aware Semantic Pruning)**
   - 原生 Android uiautomator / iOS WDA 树体积庞大 (~45,000 字符)，经过剪枝后提取为超轻量紧凑语义清单 (~600 字符，**Token 压缩率 $\ge 90\%$**)。
   - 彻底剪除所有视口外幽灵节点，杜绝 AI 操作幻觉。
   - 智能语义提升 (Semantic Hoisting)：自动将卡片内部文字提升至可点击父容器，保持语义完整。

2. **双模混合感知 (Dual-Mode Hybrid Perception)**
   - **无障碍优先 (80ms 极速响应)**：常规页面秒级感知，0 额外推理算力开销。
   - **本地 OCR 兜底 (按需激活)**：遇复杂 Canvas / Flutter / 游戏或稀疏页面自动激活轻量 ONNX OCR，补全纯视觉文字框 `@v1, @v2`。

3. **Playwright 风格 Auto-waiting 状态机**
   - 5 阶段动作就绪检查：`Attached -> Visible -> Stable (连续多周期坐标静止) -> Enabled -> Center Dispatch`。
   - 彻底杜绝进场动画未完成、页面正在滑动时的空点与漂移。

4. **双模运行栈 (Sync & Async SDK)**
   - 异步核心 (`async_api`) 支持高并发、单进程多设备调度。
   - 同步封装 (`sync_api`) 线程桥接，无缝支持快速脚本与交互式调试。

5. **原生 Model Context Protocol (MCP) 支持**
   - 提供标准 STDIO JSON-RPC 2.0 服务端。
   - 暴露 `phone_list_devices`、`phone_inspect_screen`、`phone_interact` 工具，供 ZCode、Claude Code、Cursor 等直接接入驱动真实手机。

---

## 🚀 快速上手 (Quick Start)

### 1. 同步 SDK 示例

```python
from phone_playwright import sync_phone_playwright

with sync_phone_playwright() as p:
    # 扫描并连接局域网设备 (如 OnePlus 7T)
    device = p.connect("192.168.1.3:43037")
    page = device.current_page()

    # 获取精炼快照 (极省 Token)
    snapshot = page.snapshot()
    print(snapshot.to_markdown())

    # 语义交互 (内置 Auto-waiting)
    page.locator("@2").fill("降噪耳机")
    page.locator("@1").click()

    # 支持系统手势与快捷语义
    page.get_by_text("搜索").click()
    page.swipe("down")
    page.press_back()
```

### 2. 启动 MCP 服务端

在 host 终端直接运行：

```bash
phone-playwright-mcp
# 或
python -m phone_playwright.mcp.server
```

在 AI Agent 的 `mcpServers` 配置中注册：

```json
{
  "mcpServers": {
    "phone-playwright": {
      "command": "python",
      "args": ["-m", "phone_playwright.mcp.server"],
      "cwd": "/path/to/phone-playwright"
    }
  }
}
```

---

## 📐 架构设计与文档索引

* [架构、代码与数据层骨架规范 (ARCHITECTURE_SKELETON.md)](docs/ARCHITECTURE_SKELETON.md)
* [API 契约与 MCP 协议规范 (API_SPEC.md)](docs/API_SPEC.md)
* [剪枝与状态机算法实现 (ALGORITHMS.md)](docs/ALGORITHMS.md)
* [集群自愈与跨平台驱动设计 (FLEET_AND_DRIVERS.md)](docs/FLEET_AND_DRIVERS.md)
* [混合视觉兜底与效能基准分析 (HYBRID_VISION_AND_EFFICIENCY.md)](docs/HYBRID_VISION_AND_EFFICIENCY.md)
