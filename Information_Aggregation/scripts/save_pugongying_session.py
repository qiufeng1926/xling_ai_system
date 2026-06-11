# -*- coding: utf-8 -*-
"""
蒲公英登录态保存工具

用法:
  python scripts/save_pugongying_session.py

步骤:
  1. 自动打开 Chromium 浏览器
  2. 手动登录蒲公英 https://pgy.xiaohongshu.com
  3. 登录成功后回到终端按 Enter
  4. 登录态保存到 backend/cookies/pugongying_state.json
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
BACKEND_DIR = PROJECT_DIR / "backend"
COOKIES_DIR = BACKEND_DIR / "cookies"
OUTPUT_FILE = COOKIES_DIR / "pugongying_state.json"


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("请先安装: pip install playwright")
        print("然后运行: playwright install chromium")
        sys.exit(1)

    COOKIES_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 55)
    print("  蒲公英登录态保存")
    print("=" * 55)
    print("1. 浏览器打开后，请手动登录蒲公英")
    print("2. 登录成功并进入「找博主 / 笔记博主」页面")
    print("3. 回到此终端按 Enter 保存登录态")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = context.new_page()
        page.goto("https://pgy.xiaohongshu.com/solar/pre-trade/note/kol", wait_until="domcontentloaded")

        input("\n登录完成后按 Enter 保存登录态...")

        context.storage_state(path=str(OUTPUT_FILE))
        browser.close()

    print(f"\n[SUCCESS] 登录态已保存: {OUTPUT_FILE}")
    print("\n请在 backend/.env 中配置:")
    print("  COLLECTOR_MODE=browser")
    print("  PUGONGYING_STORAGE_STATE=cookies/pugongying_state.json")


if __name__ == "__main__":
    main()
