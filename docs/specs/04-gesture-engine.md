# Phone-Playwright 高级手势引擎工程规格书 (Advanced Gesture Engine)

## 1. 业务痛点与技术诉求

移动端高级交互（如列表拖拽重排、拼图滑块验证码、双指缩放地图、九宫格连线解锁）无法通过简单的线性 `input swipe` 解决。主要问题包括：
1. **线性瞬时滑动的机械性**：`input swipe x1 y1 x2 y2 duration` 生成的是机械的匀速直线轨迹，极易触发目标 App 的风控与反作弊机制（如拼图滑块直接判定为机器人）。
2. **多点触控与缩放缺失**：原生 ADB 命令行不支持原生的双指缩放（Pinch-to-zoom）。
3. **元素级拖拽对齐困难**：缺少类似 Web Playwright 的 `locator.drag_to(target_locator)` 封装。

---

## 2. 拟人化手势数学模型 (Human-Like Trajectory Math Model)

### 2.1 三阶贝塞尔曲线平滑轨迹 (Cubic Bézier Interpolation)
任何拟人滑动轨迹均由起点 $P_0$、终点 $P_3$ 及两个动态计算的随机控制点 $P_1, P_2$ 决定。
$$B(t) = (1-t)^3 P_0 + 3(1-t)^2 t P_1 + 3(1-t) t^2 P_2 + t^3 P_3, \quad t \in [0, 1]$$

* **控制点动态扰动算法**：
  设起点为 $(x_0, y_0)$，终点为 $(x_3, y_3)$，直线距离为 $L = \sqrt{(x_3 - x_0)^2 + (y_3 - y_0)^2}$。
  引入正交法向量方向的高斯偏置 $\delta \sim \mathcal{N}(0, \sigma^2)$，其中 $\sigma = 0.08 \times L$：
  $$\begin{aligned}
  P_1 &= P_0 + \frac{1}{3}(P_3 - P_0) + \vec{n} \cdot \delta_1 \\
  P_2 &= P_0 + \frac{2}{3}(P_3 - P_0) + \vec{n} \cdot \delta_2
  \end{aligned}$$

### 2.2 变加速时钟模型 (Sigmoid Time-Warping Function)
人类手势具有明显的“加速启动 $\to$ 高速滑动 $\to$ 减速微调释放”特征。时间进度 $t \in [0, 1]$ 通过非线性 Sigmoid 映射生成实际时间序列：
$$s(\tau) = \frac{1}{1 + e^{-k(\tau - 0.5)}}, \quad \tau \in [0, 1]$$
归一化后保证 $s(0) = 0, s(1) = 1$。中间点分布密集度呈现两头稠密、中间稀疏的真实物理特征。

---

## 3. 高级手势 API 设计与契约

### 3.1 元素拖拽放置 (`drag_to`)
```python
class PhoneLocator:
    async def drag_to(
        self,
        target: PhoneLocator,
        duration_ms: int = 600,
        press_duration_ms: int = 300,
        steps: int = 25,
    ) -> ActionResult:
        """从当前元素中心点平滑拖拽至目标元素中心点。

        执行步骤:
        1. 自动等待当前元素与目标元素 Visible & Stable;
        2. 在当前元素中心点按压 press_duration_ms (触发原生拖拽准备态);
        3. 沿贝塞尔曲线多步插值滑动至目标元素中心点;
        4. 在目标点停留 50ms 后松开;
        5. 自动使温热缓存失效。
        """
```

### 3.2 双指缩放 (`pinch_in` / `pinch_out`)
```python
class AsyncPhonePage:
    async def pinch_out(
        self,
        center: Optional[tuple[int, int]] = None,
        scale: float = 2.0,
        duration_ms: int = 400,
    ) -> None:
        """双指张开 (放大): 两指从中心向外两侧平滑对称滑动。"""

    async def pinch_in(
        self,
        center: Optional[tuple[int, int]] = None,
        scale: float = 0.5,
        duration_ms: int = 400,
    ) -> None:
        """双指捏合 (缩小): 两指从外侧向中心平滑对称滑动。"""
```

### 3.3 任意连续路径手势 (`swipe_path`)
```python
class AsyncPhonePage:
    async def swipe_path(
        self,
        points: list[tuple[int, int]],
        duration_ms: int = 800,
    ) -> None:
        """多点折线连续手势 (如九宫格锁屏、复杂滑块拼图)。"""
```

---

## 4. 多平台底层驱动分发机制

### 4.1 Android 平台
1. **轻量通用通道**：将插值出的 $N$ 个离散采样点切分为子段，通过异步非阻塞流水线循环下发小步长 `input swipe`（间隔 $15\text{ms}$）。
2. **多点触控与高性能通道**：针对双指缩放与超低延迟手势，采用 Linux `/dev/input/event*`（`sendevent`）双点多路插值协议（`ABS_MT_SLOT 0` 与 `ABS_MT_SLOT 1`）。

### 4.2 iOS 平台
通过 WDA 的 `/wda/touch/perform` 与 `/wda/touch/multi/perform` 端点，直接传递标准 W3C Actions 规范的 JSON 数据包，由 XCTest 框架执行原生平滑轨迹模拟。
