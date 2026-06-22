# -*- coding: utf-8 -*-
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.collectors.base import SearchFilters
from app.collectors.xingtu_browser import XingtuBrowserCollector

OUT = BACKEND_DIR / "logs" / "test_xingtu_filter_result.json"


def run(creator_type: str | None, quote_duration: str | None, limit: int = 10):
    filters = SearchFilters(limit=limit, creator_type=creator_type, quote_duration=quote_duration)
    results = XingtuBrowserCollector().search(keyword="", filters=filters)
    payload = {
        "creator_type": creator_type,
        "quote_duration": quote_duration,
        "requested": limit,
        "count": len(results),
        "items": [
            {
                "nickname": r.nickname,
                "follower_count": r.follower_count,
                "profile_url": r.profile_url,
                "creator_type": (r.extra_data or {}).get("creator_type"),
                "tags": r.matched_tags[:5],
            }
            for r in results
        ],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    run("美妆", "21-60s", 30)
