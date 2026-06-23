# -*- coding: utf-8 -*-
"""验证旧版筛选值别名仍可点击"""
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
OUT = BACKEND_DIR / "logs" / "xingtu_filter_legacy_diag.json"


def main() -> int:
    from playwright.sync_api import sync_playwright

    from app.collectors.base import SearchFilters
    from app.collectors.xingtu_browser import XingtuBrowserCollector

    collector = XingtuBrowserCollector()
    filters = SearchFilters(
        cooperation_purpose="种草",
        cooperation_form="视频",
        creator_type="美妆",
        follower_tier="10w-50w",
        creator_gender="女",
        follower_gender="女",
        follower_age="24-30",
        theme_tags=["星图优选达人", "新锐达人"],
        limit=10,
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = collector._create_context(browser)
        page = context.new_page()
        page.goto("https://www.xingtu.cn/ad/creator/market", wait_until="domcontentloaded")
        page.wait_for_timeout(3500)
        applied = collector._apply_page_filters(page, filters)
        context.close()
        browser.close()

    OUT.write_text(json.dumps({"applied": applied, "count": len(applied)}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
