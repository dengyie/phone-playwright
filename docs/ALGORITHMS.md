# 核心算法规范：视口树蒸馏与 Auto-waiting 状态机

## 1. 算法一：视口感知树剪枝与蒸馏 (Viewport-Aware Semantic Pruning)

### 1.1 问题形式化定义
设底层驱动导出的原始无障碍树为树形结构 $T = (V, E)$，其中每个节点 $u \in V$ 具有属性：
- $B(u) = [x_1, y_1, x_2, y_2]$：绝对屏幕像素坐标边界。
- $Attr(u) = \{ clickable, focusable, scrollable, visible, enabled \}$。
- $Text(u)$：控件显示的文字内容。
- $Desc(u)$：无障碍描述（`content-description` 或 `accessibilityLabel`）。
- $Class(u)$：原生类名（如 `android.widget.TextView`, `XCUIElementTypeButton` 等）。

当前设备屏幕的物理视口几何矩形为 $VP = [0, 0, W, H]$。

**目标**：构建一个扁平化的紧凑交互列表 $L = [e_1, e_2, \dots, e_k]$，满足：
1. **零视口外幻觉**：$\forall e \in L, \text{Area}(B(e) \cap VP) > 0$ 且宽高均大于物理最小可触控阈值 $\delta_{min}$（例如 8px）。
2. **Token 最小化**：剔除所有无语义价值的纯布局中间容器（如 `FrameLayout`, `LinearLayout`）。
3. **语义完整性**：若可点击父容器包含无点击属性的文本子节点，子节点文本必须**向上提升合并（Semantic Hoisting）**，避免信息割裂。
4. **确定性寻址**：为每个留存的可操作节点分配唯一自增编号 `@index`。

### 1.2 蒸馏算法伪代码实现

```python
def prune_and_distill(root_node, screen_width, screen_height) -> list[CompactElement]:
    compact_list = []
    current_ref_id = 1
    viewport = Rect(0, 0, screen_width, screen_height)

    def is_in_viewport(bounds: Rect) -> bool:
        # 计算交集矩形
        inter = bounds.intersection(viewport)
        if inter is None:
            return False
        # 过滤掉 0 像素或极小幽灵节点（如边缘不可见占位）
        return inter.width >= 10 and inter.height >= 10

    def traverse(node):
        nonlocal current_ref_id
        
        # 1. 视口几何裁剪：不在视口内的子树直接剪除
        if not is_in_viewport(node.bounds):
            return

        # 2. 收集当前子树的文本与语义
        direct_text = node.text or ""
        direct_desc = node.desc or ""
        is_interactive = (node.clickable or node.editable or node.checkable or node.scrollable)

        # 3. 递归遍历子节点
        children_interactive = []
        for child in node.children:
            traverse(child)

        # 4. 语义提升与收缩规则：
        # 如果当前节点自身是可点击的，但它没有文本，而它的内部只包含纯文本展示的叶子：
        if is_interactive:
            aggregated_text = collect_descendant_texts(node)
            role = infer_semantic_role(node.class_name, node)
            
            element = CompactElement(
                ref=f"@{current_ref_id}",
                role=role,
                text=aggregated_text or direct_desc or direct_text,
                bounds=node.bounds,
                enabled=node.enabled,
                scrollable=node.scrollable,
                original_id=node.resource_id
            )
            compact_list.append(element)
            current_ref_id += 1
        elif direct_text or direct_desc:
            # 即使不可点击，但是带有关键信息的展示文字（例如金额、状态、标题）
            element = CompactElement(
                ref=None, # 非交互元素无 @ref，仅作感知输入
                role="text",
                text=direct_text or direct_desc,
                bounds=node.bounds
            )
            compact_list.append(element)

    traverse(root_node)
    return compact_list
```

### 1.3 产物对比

**处理前 (原生 XML, ~45,000 字符, ~11,000 Tokens)**:
```xml
<hierarchy rotation="0">
  <android.widget.FrameLayout bounds="[0,0][1080,2400]">
    <android.widget.LinearLayout bounds="[0,0][1080,2400]">
      <android.widget.RelativeLayout bounds="[0,120][1080,320]">
        <android.view.View clickable="false" bounds="[0,120][1080,320]"/>
        <android.widget.TextView text="返回" clickable="true" bounds="[30,150][120,240]"/>
...
```

**处理后 (蒸馏后 JSON, ~600 字符, ~150 Tokens, 节省 98.6% 开销)**:
```json
[
  {"ref": "@1", "role": "button", "text": "返回", "bounds": [30, 150, 120, 240]},
  {"ref": "@2", "role": "input", "hint": "搜索商品", "bounds": [150, 140, 920, 250]},
  {"role": "text", "text": "猜你喜欢", "bounds": [40, 300, 300, 360]},
  {"ref": "@3", "role": "item", "text": "一加手机无线闪充 ￥199", "bounds": [40, 380, 520, 900]}
]
```

---

## 2. 算法二：Playwright 风格的 Auto-waiting 状态机

### 2.1 状态转移图
一个交互动作（如 `click` 或 `fill`）不是简单的触发指令，而是经历如下确定性状态转移过程：

```
       [Start]
          │
          ▼
    ┌───────────┐         Timeout Exceeded
    │  Pending  ├──────────────────────────────► [Error: TimeoutError]
    └─────┬─────┘
          │ 找到元素
          ▼
    ┌───────────┐         不在视口内 / 被隐藏
    │  Attached ├──────────────────────────────► [Retry Loop]
    └─────┬─────┘
          │ 在视口内
          ▼
    ┌───────────┐         坐标变动 (移动中/动画中)
    │  Visible  ├──────────────────────────────► [Wait Stable Loop]
    └─────┬─────┘
          │ 连续 2 次采样坐标静止
          ▼
    ┌───────────┐         enabled == false
    │  Stable   ├──────────────────────────────► [Retry Loop]
    └─────┬─────┘
          │ enabled == true
          ▼
    ┌───────────┐
    │  Ready    │
    └─────┬─────┘
          │ 计算物理中心坐标 (cx, cy)
          ▼
    ┌───────────┐
    │ Dispatch  │  (下发 Tap / SendKeys)
    └─────┬─────┘
          │
          ▼
      [Success]
```

### 2.2 核心状态机执行算法

```python
class ActionabilityEngine:
    def __init__(self, driver, poll_interval_ms=100, default_timeout_s=5.0):
        self.driver = driver
        self.poll_interval = poll_interval_ms / 1000.0
        self.default_timeout = default_timeout_s

    def execute_click(self, selector: Selector, timeout_s: float = None):
        timeout = timeout_s or self.default_timeout
        start_time = time.monotonic()
        last_bounds = None
        stable_hit_count = 0

        while time.monotonic() - start_time < timeout:
            # 1. 获取当前最新紧凑树
            snapshot = self.driver.get_compact_snapshot()
            node = selector.resolve(snapshot)

            if not node:
                time.sleep(self.poll_interval)
                continue

            # 2. 检查可见性与视口
            if not node.is_visible_in_viewport():
                time.sleep(self.poll_interval)
                continue

            # 3. 稳定性检测 (Stable Check)
            current_bounds = node.bounds
            if last_bounds and current_bounds == last_bounds:
                stable_hit_count += 1
            else:
                stable_hit_count = 0
            last_bounds = current_bounds

            # 需要至少连续 2 个采样周期（约 200ms）坐标静止，确保页面无惯性滑动
            if stable_hit_count < 2:
                time.sleep(self.poll_interval)
                continue

            # 4. 检查是否处于可用状态 (Enabled Check)
            if not node.enabled:
                time.sleep(self.poll_interval)
                continue

            # 5. 命中所有 Actionability 准则，执行点击
            cx = (current_bounds.left + current_bounds.right) // 2
            cy = (current_bounds.top + current_bounds.bottom) // 2
            self.driver.tap(cx, cy)
            return True

        raise TimeoutError(f"Element matching {selector} failed actionability checks within {timeout}s")
```
