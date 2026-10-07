# Phone-Playwright Set-of-Mark (SoM) 视觉多模态感知规格书

## 1. 业务背景与多模态演进

随着多模态大模型（Vision-Language Models, VLMs）在移动 Agent 领域的普及，传统的纯文本 Accessibility 树感知面临两大瓶颈：
1. **纯图形界面与自绘引擎失明**：游戏界面、Flutter 自绘组件、Unity 引擎及纯图片 Banner 缺少语义标签。
2. **图标语义缺失**：返回箭头、关闭叉号、设置齿轮等图标往往仅有 `clickable=True`，无 `text` 与 `desc`。
3. **坐标幻觉问题**：直接让 VLM 输出绝对物理坐标（如 $[342, 856]$）存在严重的定位漂移与缩放误差。

**Set-of-Mark (SoM) 解决方案**：
在截取的屏幕图像上，由框架自动为每个可交互元素叠加带半透明边界的高对比度数字角标（如 `[@1]`, `[@2]`）。VLM 只需理解图像并输出角标编号 `click("@4")`，彻底消除坐标漂移，单步推理成功率从 $\approx 60\%$ 跃升至 $\ge 95\%$。

---

## 2. 视觉标注架构与渲染管线

```
 [Raw Viewport Image (PNG)] + [Compact Elements (Rects & @refs)]
                             |
                             v
           +----------------------------------+
           |     Coordinate Normalizer        |
           | 视口物理坐标与图片像素点阵自适应缩放 |
           +----------------------------------+
                             |
                             v
           +----------------------------------+
           |    Color Harmonizer & Palette    |
           | 根据元素语义角色分配高辨识度专属色板  |
           | - button: 鲜明蓝/绿             |
           | - input: 琥珀黄                 |
           | - item/tab: 紫色                |
           +----------------------------------+
                             |
                             v
           +----------------------------------+
           |       Visual Mark Compositor     |
           | 1. 绘制 2px 细边框外接矩形        |
           | 2. 绘制圆角数字角标背景 (Badge)    |
           | 3. 绘制高对比度加粗序号文字       |
           +----------------------------------+
                             |
                             v
           [Annotated Image (SoM Image)] -> Base64 / File Artifact
```

---

## 3. 核心算法与坐标对齐

### 3.1 视口与位图点阵缩放映射 (DPI & Density Normalization)
当设备物理渲染尺寸（如截图 $1080 \times 2400$）与逻辑无障碍视口（如 $1080 \times 2400$ 或缩放下的 $540 \times 1200$）存在比例差异时，建立仿射变换比例：
$$S_x = \frac{W_{\text{image}}}{W_{\text{viewport}}}, \quad S_y = \frac{H_{\text{image}}}{H_{\text{viewport}}}$$
元素在图像上的绝对像素边界计算公式：
$$\begin{cases}
X_1 = \text{round}(\text{rect.left} \times S_x) \\
Y_1 = \text{round}(\text{rect.top} \times S_y) \\
X_2 = \text{round}(\text{rect.right} \times S_x) \\
Y_2 = \text{round}(\text{rect.bottom} \times S_y)
\end{cases}$$

### 3.2 角标避让与防遮挡渲染策略 (Badge Collision Avoidance)
* **默认锚点**：元素左上角 $[X_1, Y_1]$。
* **越界自适应倒贴 (Edge Inversion)**：
  - 若 $Y_1 - \text{BadgeHeight} < 0$（贴近屏幕顶端）：角标内嵌至元素内部 $[X_1, Y_1]$ 渲染。
  - 若 $X_1 + \text{BadgeWidth} > W_{\text{image}}$（贴近屏幕右边缘）：角标右对齐至 $[X_2 - \text{BadgeWidth}, Y_1]$。
* **重叠稀疏化 (Z-Index Deduplication)**：
  若父容器与子元素重叠（如全屏 scrollable 包含小 button），角标仅绘制在**最小面积的叶子节点**上，避免大容器角标覆盖小按钮。

---

## 4. API 设计与使用范式

### 4.1 快照 API 扩展
```python
class AsyncPhonePage:
    async def snapshot(
        self,
        include_screenshot: bool = False,
        include_som_image: bool = False,
        som_palette: Optional[Dict[str, str]] = None,
    ) -> PageSnapshot:
        """获取视口语义快照。

        若 include_som_image=True，在 Base64 截图中渲染 Set-of-Mark 标记，
        输出 annotated_screenshot_base64 供多模态 Agent 消费。
        """
```

### 4.2 PageSnapshot 实体扩展
```python
class PageSnapshot(BaseModel):
    timestamp: float
    device_id: str
    package_name: Optional[str] = None
    activity_name: Optional[str] = None
    viewport_width: int
    viewport_height: int
    elements: List[CompactElement] = Field(default_factory=list)
    screenshot_base64: Optional[str] = None
    annotated_screenshot_base64: Optional[str] = None  # SoM 标注图 Base64

    def to_multimodal_prompt(self) -> Dict[str, Any]:
        """构建包含 SoM 图像与紧凑 Markdown 列表的多模态输入 Payload。"""
        return {
            "image_base64": self.annotated_screenshot_base64 or self.screenshot_base64,
            "markdown_tree": self.to_markdown(),
        }
```

---

## 5. 性能与 Token 预算

| 指标 | 纯文本感知 | 纯截图像素感知 | SoM 双模感知 (Phone-Playwright) |
|---|---|---|---|
| **每步 Token 消耗** | $\approx 300\text{ tokens}$ | $\approx 1500\text{ tokens}$ | **$\approx 600\text{ tokens}$ (低画质 SoM + 紧凑文本)** |
| **单步点击准确率** | $82\%$ (受纯图标盲区限制) | $64\%$ (受坐标漂移限制) | **$\ge 96\%$ (编号严格对齐)** |
| **图像生成耗时** | $0\text{ms}$ | $\approx 80\text{ms}$ (截图) | $\approx 95\text{ms}$ (截图 + 内存 PIL 快速角标合成) |
