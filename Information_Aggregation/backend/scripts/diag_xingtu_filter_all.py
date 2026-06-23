# -*- coding: utf-8 -*-
"""诊断星图各筛选项能否成功点击"""
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
OUT = BACKEND_DIR / "logs" / "xingtu_filter_all_diag.json"


def main() -> int:
    from playwright.sync_api import sync_playwright

    from app.collectors.base import SearchFilters
    from app.collectors.xingtu_browser import XingtuBrowserCollector
    from app.constants.xingtu_filters import PAGE_FILTER_CLICK, PAGE_FILTER_LABELS

    collector = XingtuBrowserCollector()
    filters = SearchFilters(
        cooperation_purpose="破圈种草",
        cooperation_form="短视频达人",
        creator_type="美妆",
        follower_tier="10w-100w",
        content_theme="美食教程与测评",
        creator_gender="女性",
        follower_gender="女性占比大于50%",
        follower_age="24-30岁居多",
        quote_duration="21-60s",
        theme_tags=["优选达人", "新面孔达人"],
        limit=10,
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = collector._create_context(browser)
        page = context.new_page()
        page.goto("https://www.xingtu.cn/ad/creator/market", wait_until="domcontentloaded")
        page.wait_for_timeout(3500)

        applied = collector._apply_page_filters(page, filters)
        active = collector._read_active_filter_chips(page)

        expected = []
        for field_key in PAGE_FILTER_CLICK:
            value = getattr(filters, field_key, None)
            if value:
                row_label = PAGE_FILTER_LABELS.get(field_key, field_key)
                expected.append(f"{row_label}={value}")
        if filters.theme_tags:
            for tag in filters.theme_tags:
                expected.append(f"主题={tag}")

        payload = {
            "expected_count": len(expected),
            "applied_count": len(applied),
            "applied": applied,
            "missing": [e for e in expected if not any(e.split("=")[0] in a for a in applied)],
            "active_chips": active,
        }
        context.close()
        browser.close()

    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
