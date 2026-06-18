"""批量用当前 AI 总结系统重新生成已有会议的 Markdown + 图文速览。

用法:
  python scripts/regenerate_summaries.py --name-pattern 熵函数
  python scripts/regenerate_summaries.py --file-id f3a58879-5a7e-4785-8628-63c618b8792f
  python scripts/regenerate_summaries.py --name-pattern 熵函数 --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from config.config import database_url, output_dir
from db.models import Meeting, init_database, migrate_schema
from db.session import SessionFactory, update_meeting_summaries
from llm.client_holder import create_llm_client
from llm.summary_service import dual_result_to_db_fields, generate_dual_summaries
from sqlalchemy import create_engine, or_


def _load_transcript(meeting: Meeting) -> str:
    text = (meeting.transcript or "").strip()
    if text:
        return text
    path = meeting.transcript_file_path
    if path and Path(path).is_file():
        return Path(path).read_text(encoding="utf-8").strip()
    return ""


def _find_meetings(
    db,
    *,
    name_pattern: str | None,
    file_ids: list[str],
) -> list[Meeting]:
    q = db.query(Meeting).order_by(Meeting.created_at.asc())
    if file_ids:
        return q.filter(Meeting.file_id.in_(file_ids)).all()
    if name_pattern:
        like = f"%{name_pattern.strip()}%"
        return q.filter(
            or_(
                Meeting.meeting_name.like(like),
                Meeting.original_filename.like(like),
            )
        ).all()
    raise SystemExit("请指定 --name-pattern 或 --file-id")


def _write_summary_files(meeting: Meeting, summary: str, visual_json: str | None) -> str | None:
    summaries_dir = Path(output_dir) / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)

    summary_path = meeting.summary_file_path
    if summary_path:
        path = Path(summary_path)
    else:
        safe = "".join(
            c for c in (meeting.meeting_name or "meeting")
            if c.isalnum() or c in (" ", "-", "_")
        ).strip() or "meeting"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = summaries_dir / f"{safe}_{meeting.file_id}_{ts}_regen.md"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(summary, encoding="utf-8")

    if visual_json:
        visual_path = path.with_name(path.stem + "_visual.json")
        visual_path.write_text(visual_json, encoding="utf-8")

    return str(path)


async def regenerate_one(meeting: Meeting, *, dry_run: bool) -> None:
    transcript = _load_transcript(meeting)
    if not transcript:
        print(f"  跳过 {meeting.file_id}: 无转写内容")
        return

    title = meeting.meeting_name or meeting.file_id
    print(f"  处理 {title} ({meeting.file_id[:8]}…, {len(transcript)} 字)")
    if dry_run:
        return

    started = meeting.created_at
    llm_start = time.time()
    dual = await generate_dual_summaries(
        create_llm_client(),
        transcript,
        meeting.meeting_name,
        started,
    )
    llm_ms = round((time.time() - llm_start) * 1000)

    if dual.markdown_error or not dual.markdown:
        raise RuntimeError(dual.markdown_error or "Markdown 速览生成失败")

    fields = dual_result_to_db_fields(dual)
    summary_path = _write_summary_files(meeting, dual.markdown, dual.visual_json)

    update_meeting_summaries(
        meeting.file_id,
        summary=fields["summary"],
        summary_visual=fields.get("summary_visual"),
        summary_visual_status=fields.get("summary_visual_status"),
        summary_file_path=summary_path,
        llm_duration_ms=llm_ms,
    )
    print(
        f"    完成: summary={len(dual.markdown)} 字, "
        f"visual={fields.get('summary_visual_status')}, llm={llm_ms}ms"
    )


async def main_async(args: argparse.Namespace) -> None:
    init_database(database_url)
    migrate_schema(create_engine(database_url))

    db = SessionFactory()
    try:
        meetings = _find_meetings(
            db,
            name_pattern=args.name_pattern,
            file_ids=args.file_id or [],
        )
        if not meetings:
            print("未找到匹配的会议记录")
            return

        print(f"共 {len(meetings)} 条会议" + ("（预览，不写入）" if args.dry_run else ""))
        for meeting in meetings:
            await regenerate_one(meeting, dry_run=args.dry_run)
        print("全部处理完毕，可在 xlink「会议记录」中刷新查看。")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="重新生成会议 AI 总结")
    parser.add_argument("--name-pattern", help="按会议名称/文件名模糊匹配，如 熵函数")
    parser.add_argument(
        "--file-id",
        action="append",
        default=[],
        help="指定 file_id，可重复传入",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅列出将处理的会议，不调用 LLM")
    args = parser.parse_args()
    if not args.name_pattern and not args.file_id:
        parser.error("请指定 --name-pattern 或 --file-id")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
