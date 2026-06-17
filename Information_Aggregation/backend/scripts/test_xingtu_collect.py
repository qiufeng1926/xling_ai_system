# -*- coding: utf-8 -*-
"""单次星图采集冒烟测试（仅 1 次页面访问，不访问详情页）"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.collectors.base import SearchFilters
from app.collectors.xingtu_browser import XingtuBrowserCollector


def main() -> int:
    keyword = sys.argv[1] if len(sys.argv) > 1 else "美食"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    filters = SearchFilters(limit=limit)
    results = XingtuBrowserCollector().search(keyword=keyword, filters=filters)

    payload = [
        {
            "nickname": r.nickname,
            "platform_uid": r.platform_uid,
            "follower_count": r.follower_count,
            "match_score": r.match_score,
            "matched_tags": r.matched_tags[:5],
            "engagement_rate": r.engagement_rate,
        }
        for r in results
    ]
    out = BACKEND_DIR / "logs" / "test_xingtu_result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"keyword": keyword, "count": len(payload), "items": payload}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
