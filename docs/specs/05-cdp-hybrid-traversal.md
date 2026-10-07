# Phone-Playwright 混合应用 (WebView/小程序) CDP 穿透规格书

## 1. 业务痛点与技术边界

现代移动应用（如微信小程序、淘宝/京东、美团、各类金融 Hybrid App）大量采用 WebView 技术构建界面。
在传统的原生 Accessibility / UIAutomator 体系下存在天然屏障：
1. **黑盒化与扁平化 (Black-Box View)**：系统无障碍树只能将整个 WebView 呈现为一个巨大的 `android.webkit.WebView` 矩形容器，内部所有的 HTML DOM 节点、CSS 样式、按钮及输入框均无法直接探测。
2. **文本缺失与定位不可达**：H5 动态渲染的内容、Canvas 图表及前端框架（Vue/React）虚拟 DOM 在原生层几乎全盲。

**解决方案：Chrome DevTools Protocol (CDP) 原生穿透**：
`phone-playwright` 引入轻量级 CDP 桥接引擎，直接通过 Unix Domain Socket 与 App 内嵌的 Chromium 内核建立 WebSocket 连接，实现**原生 App 控件与 H5 内部 DOM 的统一定位与混合编排**。

---

## 2. 混合穿透拓扑与自动发现管线

```
+-------------------------------------------------------------------------+
|                  Phone-Playwright Unified Page Session                  |
|  - Native Page Locators (Accessibility Tree / SoM)                      |
|  - page.frame_locator("webview_selector") -> Web Frame Locator          |
+-------------------------------------------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                     CDP Auto-Discovery Engine                           |
|  1. 扫描 /proc/net/unix 提取 @*_devtools_remote_* 套接字                |
|  2. 解析目标进程 PID 与 PackageName (匹配当前前台活跃 App)               |
|  3. 建立 ADB 端口转发: adb forward tcp:9222 localabstract:devtools_...  |
|  4. HTTP GET http://127.0.0.1:9222/json/list 获取活跃 Page / Target ID  |
+-------------------------------------------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                 Lightweight CDP JSON-RPC Client (AsyncIO)               |
|  - DOM.getDocument / DOM.querySelector / DOM.getBoxModel                |
|  - Runtime.evaluate / Page.navigate / Input.dispatchMouseEvent          |
+-------------------------------------------------------------------------+
                                     | (Chromium WebSocket Engine)
                                     v
+-------------------------------------------------------------------------+
|                    In-App WebView / XWeb Core                           |
+-------------------------------------------------------------------------+
```

---

## 3. 自动发现与套接字路由算法

### 3.1 Unix Domain Socket 探测
执行 `cat /proc/net/unix`，过滤出包含 `devtools_remote` 的抽象命名空间套接字：
* 标准 Chrome / Chromium：`@chrome_devtools_remote`
* 原生 Android WebView：`@webview_devtools_remote_<PID>`
* 腾讯 XWeb (微信/QQ 小程序)：`@xweb_devtools_remote_<PID>`

### 3.2 活跃前台进程自动对准
1. 通过 `get_current_app()` 获取当前前台进程的 `package_name` 与 `pid`。
2. 将过滤到的 `devtools_remote_<PID>` 套接字与当前前台 PID 进行 $O(1)$ 映射，杜绝端口转发到后台无关应用。
3. 动态分配本地空闲端口（如 `9222`），执行：
   ```bash
   adb forward tcp:9222 localabstract:webview_devtools_remote_<PID>
   ```

---

## 4. 统一 FrameLocator API 与混合交互

### 4.1 FrameLocator 声明与使用
```python
class AsyncPhonePage:
    def frame_locator(self, selector: str = "role=scrollable") -> WebFrameLocator:
        """根据原生选择器定位 WebView 容器，并返回内嵌 Web 树定位器。"""
        return WebFrameLocator(page=self, container_selector=selector)

class WebFrameLocator:
    def locator(self, css_or_xpath: str) -> WebPhoneLocator:
        """通过 CSS 选择器或 XPath 查询 WebView 内部 DOM 节点。"""
        return WebPhoneLocator(frame=self, selector=css_or_xpath)

    async def title(self) -> str:
        """获取 WebView 内部 HTML document.title。"""

    async def url(self) -> str:
        """获取当前 H5 页面 window.location.href。"""
```

### 4.2 坐标系绝对映射与物理点击闭环
1. 通过 CDP 获取内嵌 DOM 节点的相对视口边界：`{x: 50, y: 120, width: 200, height: 40}`。
2. 获取宿主原生 WebView 组件的绝对屏幕边界：`{left: 0, top: 150, right: 1080, bottom: 2000}`。
3. 计算最终物理像素点击坐标：
   $$X_{\text{physical}} = \text{WebView.left} + x + \frac{\text{width}}{2}$$
   $$Y_{\text{physical}} = \text{WebView.top} + y + \frac{\text{height}}{2}$$
4. 既可通过 CDP 原生 `Input.dispatchMouseEvent` 直接分发，亦可通过底层 ADB `input tap` 分发，完全兼容物理手势。

---

## 5. 常见限制与生产防御

| 限制场景 | 表现与成因 | 框架自愈与绕过策略 |
|---|---|---|
| **`setWebContentsDebuggingEnabled` 未开启** | 正式包禁用了 WebView 调试开关，无法产生 Unix Socket | 自动平滑降级至 **SoM 视觉多模态标注 + OCR 方案**，保证用例不中断 |
| **小程序多进程隔离** | 小程序 Render 进程与 Main 进程分离 | 递归枚举所有关联子 PID，建立多 Target 动态路由池 |
| **页面跳转导致 WebSocket 断开** | H5 单页路由跳转或重定向 | 内置 WebSocket 心跳保活与 `Page.frameNavigated` 自动重连监听 |
