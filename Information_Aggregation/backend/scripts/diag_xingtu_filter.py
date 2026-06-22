# -*- coding: utf-8 -*-
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
OUT = BACKEND_DIR / "logs" / "xingtu_filter_diag.json"


def main() -> int:
    from playwright.sync_api import sync_playwright

    from app.collectors.base import SearchFilters
    from app.collectors.xingtu_browser import XingtuBrowserCollector
    from app.config import settings

    collector = XingtuBrowserCollector()
    filters = SearchFilters(creator_type="美妆", quote_duration="21-60s", limit=10)
    api_urls: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = collector._create_context(browser)
        page = context.new_page()

        def on_response(response) -> None:
            url = response.url
            if "search_for_author" in url:
                api_urls.append(url)

        page.on("response", on_response)
        page.goto("https://www.xingtu.cn/ad/creator/market", wait_until="domcontentloaded")
        page.wait_for_timeout(3500)

        applied = collector._apply_page_filters(page, filters)
        collector._wait_for_results_refresh(page)
        collector._scroll_to_results_area(page)

        shot = BACKEND_DIR / "logs" / "screenshots" / "filter_diag.png"
        shot.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(shot), full_page=True)

        payload = {
            "applied": applied,
            "active_chips": collector._read_active_filter_chips(page),
            "api_urls": api_urls[-5:],
            "screenshot": str(shot),
        }
        context.close()
        browser.close()

    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
