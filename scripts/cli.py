#!/usr/bin/env python3
"""phone-playwright 独立命令行工具 (CLI & REPL & MCP 启动器)

支持非交互与交互式调用：
  - 快照审查:   python scripts/cli.py --device <id> snapshot
  - 元素点击:   python scripts/cli.py --device <id> click "text=设置"
  - 文本输入:   python scripts/cli.py --device <id> fill "resource-id=search_src_text" "无线网络"
  - 滚动搜寻:   python scripts/cli.py --device <id> scroll "text=关于本机"
  - 滑动手势:   python scripts/cli.py --device <id> swipe up
  - 启动 MCP:   python scripts/cli.py --device <id> mcp
  - 交互 REPL:  python scripts/cli.py --device <id> repl
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# 将 src 加入模块导入搜索路径，确保自包含开箱即用
SKILL_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = SKILL_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from phone_playwright.api.async_api import AsyncPhonePlaywright
from phone_playwright.mcp.server import PhonePlaywrightMcpServer


async def run_snapshot(device_id: str, screenshot: bool = False) -> None:
    async with AsyncPhonePlaywright() as pw:
        device = await pw.connect(device_id)
        page = device.page
        snap = await page.snapshot(include_screenshot=screenshot)
        print(f"=== 设备快照 (包名: {snap.package_name}, 活动: {snap.activity_name}) ===")
        print(f"视口元素数量: {len(snap.elements)}")
        print(snap.summary_markdown)
        if screenshot and snap.screenshot_base64:
            print(f"[截图数据已获取，Base64 字符长度: {len(snap.screenshot_base64)}]")


async def run_click(device_id: str, selector: str, timeout: float) -> None:
    async with AsyncPhonePlaywright() as pw:
        device = await pw.connect(device_id)
        page = device.page
        result = await page.locator(selector).click(timeout_s=timeout)
        print(f"[成功] 点击完成: 目标 '{selector}', 耗时 {result.time_taken_ms}ms, 坐标范围: {result.executed_at_bounds}")


async def run_fill(device_id: str, selector: str, text: str, timeout: float) -> None:
    async with AsyncPhonePlaywright() as pw:
        device = await pw.connect(device_id)
        page = device.page
        result = await page.locator(selector).fill(text, timeout_s=timeout)
        print(f"[成功] 文本输入完成: 目标 '{selector}', 输入内容 '{text}', 耗时 {result.time_taken_ms}ms")


async def run_scroll(device_id: str, selector: str, max_swipes: int, direction: str) -> None:
    async with AsyncPhonePlaywright() as pw:
        device = await pw.connect(device_id)
        page = device.page
        loc = await page.locator(selector).scroll_into_view(max_swipes=max_swipes, direction=direction)  # type: ignore[arg-type]
        is_vis = await loc.is_visible()
        if is_vis:
            print(f"[成功] 目标 '{selector}' 已成功滚动至当前可视视口内！")
        else:
            print(f"[警告] 经过 {max_swipes} 次滑动，目标 '{selector}' 仍未出现在当前视口中。")


async def run_swipe(device_id: str, direction: str, distance_ratio: float) -> None:
    async with AsyncPhonePlaywright() as pw:
        device = await pw.connect(device_id)
        page = device.page
        await page.swipe(direction=direction, distance_ratio=distance_ratio)  # type: ignore[arg-type]
        print(f"[成功] 手势执行完成: 方向 '{direction}', 距离比例 {distance_ratio}")


async def run_repl(device_id: str) -> None:
    print(f"正在连接设备 {device_id} 进入 Phone-Playwright REPL...")
    async with AsyncPhonePlaywright() as pw:
        device = await pw.connect(device_id)
        page = device.page
        print("连接成功！可用指令: snap, click <sel>, fill <sel> <text>, scroll <sel>, swipe <dir>, back, home, exit")
        loop = asyncio.get_running_loop()
        while True:
            try:
                line = await loop.run_in_executor(None, input, "phone-pw> ")
            except (EOFError, KeyboardInterrupt):
                break
            cmd = line.strip()
            if not cmd:
                continue
            parts = cmd.split(maxsplit=2)
            verb = parts[0].lower()
            if verb in ("exit", "quit"):
                break
            elif verb == "snap":
                snap = await page.snapshot()
                print(snap.summary_markdown)
            elif verb == "click" and len(parts) >= 2:
                sel = parts[1]
                res = await page.locator(sel).click()
                print(f"Click: {res.time_taken_ms}ms")
            elif verb == "fill" and len(parts) >= 3:
                sel, text = parts[1], parts[2]
                res = await page.locator(sel).fill(text)
                print(f"Fill: {res.time_taken_ms}ms")
            elif verb == "scroll" and len(parts) >= 2:
                sel = parts[1]
                await page.locator(sel).scroll_into_view()
                print(f"Scrolled into view: {sel}")
            elif verb == "swipe" and len(parts) >= 2:
                await page.swipe(direction=parts[1])  # type: ignore[arg-type]
                print(f"Swiped {parts[1]}")
            elif verb == "back":
                await page.press_back()
                print("Pressed Back")
            elif verb == "home":
                await page.press_home()
                print("Pressed Home")
            else:
                print(f"未知或参数不足指令: {cmd}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Phone-Playwright CLI")
    parser.add_argument(
        "--device", "-d",
        default=os.getenv("ANDROID_SERIAL"),
        help="设备 ID 或 IP:端口 (默认从 ANDROID_SERIAL 读取；未指定时自动探测唯一在线设备)",
    )
    
    subparsers = parser.add_subparsers(dest="subcommand", help="子命令")
    
    # snapshot
    snap_p = subparsers.add_parser("snapshot", help="获取当前页面紧凑语义快照")
    snap_p.add_argument("--screenshot", action="store_true", help="包含截图 Base64")
    
    # click
    click_p = subparsers.add_parser("click", help="点击目标元素")
    click_p.add_argument("selector", help="选择器 (text=..., resource-id=..., @index 等)")
    click_p.add_argument("--timeout", type=float, default=5.0, help="超时时间 (秒)")
    
    # fill
    fill_p = subparsers.add_parser("fill", help="输入文本")
    fill_p.add_argument("selector", help="选择器")
    fill_p.add_argument("text", help="输入的文本内容")
    fill_p.add_argument("--timeout", type=float, default=5.0, help="超时时间 (秒)")
    
    # scroll
    scroll_p = subparsers.add_parser("scroll", help="滚动搜寻目标元素至视口内")
    scroll_p.add_argument("selector", help="选择器")
    scroll_p.add_argument("--swipes", type=int, default=5, help="最大滑动次数")
    scroll_p.add_argument("--direction", choices=["up", "down"], default="up", help="滑动方向")
    
    # swipe
    swipe_p = subparsers.add_parser("swipe", help="执行滑动手势")
    swipe_p.add_argument("direction", choices=["up", "down", "left", "right"], help="滑动方向")
    swipe_p.add_argument("--distance", type=float, default=0.5, help="滑动距离比例")
    
    # repl
    subparsers.add_parser("repl", help="启动交互式 REPL 控制台")
    
    # mcp
    subparsers.add_parser("mcp", help="启动 MCP STDIO JSON-RPC 2.0 服务")
    
    args = parser.parse_args()
    
    if args.subcommand == "snapshot":
        asyncio.run(run_snapshot(args.device, args.screenshot))
    elif args.subcommand == "click":
        asyncio.run(run_click(args.device, args.selector, args.timeout))
    elif args.subcommand == "fill":
        asyncio.run(run_fill(args.device, args.selector, args.text, args.timeout))
    elif args.subcommand == "scroll":
        asyncio.run(run_scroll(args.device, args.selector, args.swipes, args.direction))
    elif args.subcommand == "swipe":
        asyncio.run(run_swipe(args.device, args.direction, args.distance))
    elif args.subcommand == "repl":
        asyncio.run(run_repl(args.device))
    elif args.subcommand == "mcp":
        server = PhonePlaywrightMcpServer(device_id=args.device)
        asyncio.run(server.run_stdio())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
