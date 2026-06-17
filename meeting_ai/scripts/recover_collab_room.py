"""恢复因 merged_transcript 超长而卡在 ending 状态的协作会议。

用法:
  python scripts/recover_collab_room.py O2X0U6
  python scripts/recover_collab_room.py --file-id f3a58879-5a7e-4785-8628-63c618b8792f
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from config.config import database_url
from db.models import CollaborativeRoom, init_database, migrate_schema
from db.session import SessionFactory
from api.collaborative_ws import finalize_collaborative_room
from services import collaborative_service as svc
from sqlalchemy import create_engine


async def recover(room_code: str | None, file_id: str | None) -> None:
    init_database(database_url)
    migrate_schema(create_engine(database_url))

    db = SessionFactory()
    try:
        q = db.query(CollaborativeRoom)
        if room_code:
            room = q.filter(CollaborativeRoom.room_code == room_code.upper()).first()
        elif file_id:
            room = q.filter(CollaborativeRoom.file_id == file_id).first()
        else:
            raise SystemExit("请指定 room_code 或 file_id")

        if not room:
            raise SystemExit("未找到协作会议房间")

        if room.status == "completed":
            print(f"房间 {room.room_code} 已是 completed，无需恢复")
            return

        merged, hint = svc.prepare_room_recovery(db, room)
        print(f"开始恢复房间 {room.room_code}（{room.meeting_name}）… {hint}")
        await finalize_collaborative_room(db, room)
        db.refresh(room)
        print(f"恢复完成: status={room.status}, file_id={room.file_id}")
        print("请在 xlink 平台「会议记录」或 meeting_ai 历史会议中查看。")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="恢复卡住的协作会议")
    parser.add_argument("room_code", nargs="?", help="房间码，如 O2X0U6")
    parser.add_argument("--file-id", help="会议 file_id")
    args = parser.parse_args()
    if not args.room_code and not args.file_id:
        parser.error("请提供 room_code 或 --file-id")
    asyncio.run(recover(args.room_code, args.file_id))


if __name__ == "__main__":
    main()
