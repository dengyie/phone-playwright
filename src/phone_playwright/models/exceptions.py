"""统一异常体系与错误屏障定义。"""

from __future__ import annotations


class PhonePlaywrightError(Exception):
    """所有 Phone-Playwright 系统异常的基类。"""

    def __init__(self, message: str, suggestion: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.suggestion = suggestion or "检查设备状态与操作参数"

    def __str__(self) -> str:
        if self.suggestion:
            return f"{self.message} (建议: {self.suggestion})"
        return self.message


class DeviceOfflineError(PhonePlaywrightError):
    """物理设备离线或连接失败。"""

    def __init__(self, device_id: str, reason: str = "") -> None:
        msg = f"设备 {device_id} 当前离线不可达: {reason}" if reason else f"设备 {device_id} 当前离线不可达"
        super().__init__(
            message=msg,
            suggestion="请检查设备是否连接相同 Wi-Fi 局域网、是否已开启无线调试配对",
        )


class ActionabilityTimeoutError(PhonePlaywrightError):
    """元素在超时窗口内未能满足可交互性准则 (Visible, Stable, Enabled)。"""

    def __init__(self, selector: str, timeout_s: float, details: str = "") -> None:
        msg = f"元素 '{selector}' 在 {timeout_s}s 内未能达到就绪状态: {details}" if details else f"元素 '{selector}' 在 {timeout_s}s 内未能达到就绪状态"
        super().__init__(
            message=msg,
            suggestion="可能界面正在加载、存在弹窗遮挡或坐标正处于高速滑动状态",
        )


class SelectorNotFoundError(PhonePlaywrightError):
    """给定的选择器未命中任何节点。"""

    def __init__(self, selector: str) -> None:
        super().__init__(
            message=f"选择器 '{selector}' 未命中任何节点",
            suggestion="请重新调用 page.snapshot() 获取最新的 @ref 交互清单",
        )


class OffscreenElementError(PhonePlaywrightError):
    """元素处于屏幕视口之外，无法执行物理交互。"""

    def __init__(self, selector: str) -> None:
        super().__init__(
            message=f"元素 '{selector}' 处于当前物理屏幕视口之外",
            suggestion="请先调用 page.swipe('up') 或 page.swipe('down') 将元素滚动至可视区域",
        )
