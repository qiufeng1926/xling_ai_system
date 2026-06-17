# -*- coding: utf-8 -*-
"""诊断星图搜索页：输出 UTF-8 到文件，避免终端乱码"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

OUT = BACKEND_DIR / "logs" / "xingtu_diag.json"


def main() -> int:
    from urllib.parse import quote

    from playwright.sync_api import sync_playwright

    from app.config import settings
    from app.collectors.xingtu_browser import XingtuBrowserCollector

    keyword = sys.argv[1] if len(sys.argv) > 1 else "美食"
    collector = XingtuBrowserCollector()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = collector._create_context(browser)
        page = context.new_page()
        url = f"https://www.xingtu.cn/ad/creator/market?keyword={quote(keyword)}"
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3500)
        table = collector._parse_market_table(page)
        cards = collector._parse_result_cards(page)
        payload = {
            "keyword": keyword,
            "page_url": page.url,
            "table_count": len(table),
            "card_count": len(cards),
            "table_nicknames": [
                (row.get("nick_name") or row.get("nickname") or "") for row in table[:10]
            ],
            "card_nicknames": [
                (row.get("nick_name") or row.get("nickname") or "") for row in cards[:10]
            ],
        }
        context.close()
        browser.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
