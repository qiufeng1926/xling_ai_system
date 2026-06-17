# -*- coding: utf-8 -*-
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

OUT = BACKEND_DIR / "logs" / "xingtu_api_diag.json"


def main() -> int:
    from urllib.parse import quote

    from playwright.sync_api import sync_playwright

    from app.collectors.xingtu_browser import XingtuBrowserCollector, _extract_author_items
    from app.utils.collector_uid import pick_display_nickname, resolve_xingtu_platform_uid

    keyword = sys.argv[1] if len(sys.argv) > 1 else "美食"
    collector = XingtuBrowserCollector()
    hits: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = collector._create_context(browser)
        page = context.new_page()

        def on_response(response) -> None:
            if response.status != 200 or "json" not in response.headers.get("content-type", ""):
                return
            url = response.url
            if "xingtu.cn" not in url:
                return
            try:
                data = response.json()
                items = _extract_author_items(data)
                if not items:
                    return
                sample = []
                for item in items[:5]:
                    sample.append(
                        {
                            "uid": resolve_xingtu_platform_uid(item),
                            "nickname": pick_display_nickname(item, "douyin"),
                            "tags": item.get("tags") or item.get("content_tags") or item.get("tag_list"),
                        }
                    )
                hits.append({"url": url, "count": len(items), "sample": sample})
            except Exception:
                pass

        page.on("response", on_response)
        page.goto(
            f"https://www.xingtu.cn/ad/creator/market?keyword={quote(keyword)}",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        page.wait_for_timeout(4000)
        context.close()
        browser.close()

    OUT.write_text(json.dumps({"keyword": keyword, "hits": hits}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
