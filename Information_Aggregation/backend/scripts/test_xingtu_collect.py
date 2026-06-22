# -*- coding: utf-8 -*-
"""星图采集测试：支持关键词 + 筛选，结果写入 logs/test_xingtu_result.json"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.collectors.base import SearchFilters
from app.collectors.xingtu_browser import XingtuBrowserCollector

OUT = BACKEND_DIR / "logs" / "test_xingtu_result.json"


def main() -> int:
    keyword = sys.argv[1] if len(sys.argv) > 1 else ""
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    filters = SearchFilters(
        limit=limit,
        creator_type=sys.argv[3] if len(sys.argv) > 3 else None,
        quote_duration=sys.argv[4] if len(sys.argv) > 4 else None,
    )

    results = XingtuBrowserCollector().search(keyword=keyword, filters=filters)

    payload = {
        "keyword": keyword or "(无)",
        "filters": {
            "creator_type": filters.creator_type,
            "quote_duration": filters.quote_duration,
            "limit": filters.limit,
        },
        "count": len(results),
        "items": [
            {
                "nickname": r.nickname,
                "platform_uid": r.platform_uid,
                "follower_count": r.follower_count,
                "match_score": r.match_score,
                "matched_tags": r.matched_tags[:5],
                "engagement_rate": r.engagement_rate,
                "extra_creator_type": (r.extra_data or {}).get("creator_type"),
            }
            for r in results
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
