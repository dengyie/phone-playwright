#!/usr/bin/env python3
"""phone-playwright 快速 UI 视口元素检查工具

快速抓取设备当前界面的紧凑语义元素表，用于提示词调试与元素定位确认。
用法:
    python scripts/inspect_ui.py [--device <id>] [--save-screenshot <path>]
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = SKILL_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from phone_playwright.api.async_api import AsyncPhonePlaywright


async def inspect_ui(device_id: str, save_screenshot: str | None = None) -> None:
    async with AsyncPhonePlaywright() as pw:
        device = await pw.connect(device_id)
        page = device.page
        snap = await page.snapshot(include_screenshot=bool(save_screenshot))
        
        print("=" * 80)
        print(f"设备 ID:        {device_id}")
        print(f"当前包名:      {snap.package_name}")
        print(f"当前活动:      {snap.activity_name}")
        print(f"视口元素总数:  {len(snap.elements)}")
        print("=" * 80)
        print(snap.summary_markdown)
        print("=" * 80)
        
        if save_screenshot and snap.screenshot_base64:
            import base64
            img_data = base64.b64decode(snap.screenshot_base64)
            out_path = Path(save_screenshot)
            out_path.write_bytes(img_data)
            print(f"[截图已保存至: {out_path.resolve()}]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Phone-Playwright UI Inspector")
    parser.add_argument(
        "--device", "-d",
        default=os.getenv("ANDROID_SERIAL"),
        help="设备 ID 或 IP:端口 (默认从 ANDROID_SERIAL 读取；未指定时自动探测唯一在线设备)",
    )
    parser.add_argument(
        "--save-screenshot", "-s",
        help="保存截图文件路径 (例如: screenshot.png)"
    )
    args = parser.parse_args()
    asyncio.run(inspect_ui(args.device, args.save_screenshot))


if __name__ == "__main__":
    main()
