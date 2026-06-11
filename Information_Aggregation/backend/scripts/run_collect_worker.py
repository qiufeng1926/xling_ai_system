# -*- coding: utf-8 -*-
"""独立进程执行星图 Playwright 采集（避免 Windows 线程问题）"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.utils.logging_config import setup_logging

setup_logging("collect-worker")


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "missing task_id"}))
        sys.exit(1)

    task_id = int(sys.argv[1])

    from datetime import datetime

    from app.collectors.base import SearchFilters
    from app.collectors.registry import get_collector
    from app.database import SessionLocal
    from app.models import CollectedInfluencer, CollectionTask, Influencer

    db = SessionLocal()
    try:
        task = db.query(CollectionTask).filter(CollectionTask.id == task_id).first()
        if not task:
            print(json.dumps({"ok": False, "error": f"task {task_id} not found"}))
            sys.exit(1)

        task.status = "running"
        task.started_at = datetime.now()
        task.error_message = None
        db.commit()

        filters_data = task.filters or {}
        search_filters = SearchFilters.from_dict(filters_data)

        collector = get_collector(task.platform)
        results = collector.search(keyword=task.keyword, filters=search_filters)

        library_map = {
            row.platform_uid: row.id
            for row in db.query(Influencer).filter(Influencer.platform == task.platform).all()
        }

        existing_uids = {
            r[0]
            for r in db.query(CollectedInfluencer.platform_uid)
            .filter(
                CollectedInfluencer.task_id == task_id,
                CollectedInfluencer.platform == task.platform,
            )
            .all()
        }

        saved = 0
        for item in results:
            if item.platform_uid in existing_uids:
                continue

            extra = dict(item.extra_data or {})
            if item.platform_uid in library_map:
                extra["in_library"] = True
                extra["existing_influencer_id"] = library_map[item.platform_uid]

            db.add(
                CollectedInfluencer(
                    task_id=task.id,
                    platform=item.platform,
                    platform_uid=item.platform_uid,
                    nickname=item.nickname,
                    avatar_url=item.avatar_url,
                    profile_url=item.profile_url,
                    follower_count=item.follower_count,
                    engagement_rate=item.engagement_rate,
                    avg_views=item.avg_views,
                    source=item.source,
                    matched_tags=item.matched_tags,
                    match_score=item.match_score,
                    extra_data=extra or None,
                    review_status="pending",
                )
            )
            existing_uids.add(item.platform_uid)
            saved += 1

        task.status = "completed"
        task.result_count = saved
        task.completed_at = datetime.now()
        db.commit()
        print(json.dumps({"ok": True, "count": saved}))

    except Exception as exc:
        db.rollback()
        task = db.query(CollectionTask).filter(CollectionTask.id == task_id).first()
        if task:
            task.status = "failed"
            task.error_message = str(exc)
            task.error_category = None
            task.completed_at = datetime.now()
            db.commit()
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
