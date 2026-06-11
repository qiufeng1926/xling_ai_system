"""协作会议 WebSocket 处理"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from fastapi import WebSocket, WebSocketDisconnect

from api.routes.websocket import _run_with_keepalive, manager
from asr.tingwu_realtime import TingwuRealtimeEngine
from config.config import collab_max_recorders, output_dir
from db.models import CollaborativeRoom
from db.session import SessionFactory, save_meeting_to_db_async
from llm.client_holder import get_glm_client
from llm.summary_service import generate_dual_summaries, visual_dict_from_result
from services import collaborative_service as collab_svc
from services.room_runtime import TranscriptLine, room_manager
from utils.executors import run_io
from utils.logger import get_logger

logger = get_logger("collaborative_ws")
tingwu_engine = TingwuRealtimeEngine()

_SPEAKER_PREFIX_RE = re.compile(r"^\[说话人\d+\]\s*")


def _strip_speaker_prefix(text: str) -> str:
    return _SPEAKER_PREFIX_RE.sub("", text or "").strip()


async def handle_collaborative_ws(
    websocket: WebSocket,
    connection_id: str,
    current_user,
    room_code: str,
    start_time: float,
) -> None:
    session_info: dict | None = None
    db = SessionFactory()
    try:
        room = collab_svc.get_room_by_code(db, room_code.upper())
        if not room:
            await manager.send_json(connection_id, {"type": "error", "message": "会议不存在"})
            return
        if not collab_svc.can_access_room(db, room, current_user.username):
            await manager.send_json(connection_id, {"type": "error", "message": "无权加入该会议"})
            return
        try:
            collab_svc.join_room(db, room, current_user)
        except ValueError as exc:
            await manager.send_json(connection_id, {"type": "error", "message": str(exc)})
            return

        role = collab_svc._resolve_role(db, room, current_user.username) or "viewer"
        nickname = current_user.nickname or current_user.username

        async def sender(conn_id: str, payload: dict) -> None:
            await manager.send_json(conn_id, payload)

        room_manager.register_sender(connection_id, sender)
        await room_manager.join(
            room.room_code,
            connection_id,
            current_user.username,
            nickname,
            role,
            room.file_id,
            room.host_username,
            room.status,
        )

        rt = room_manager.get_room(room.room_code)
        if rt and not rt.transcript_lines and room.merged_transcript:
            for line in (room.merged_transcript or "").strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                m = re.match(r"^\[(.+?)\]\s*(.+)$", line)
                if m:
                    line_nickname, text = m.group(1), m.group(2)
                    rt.transcript_lines.append(
                        TranscriptLine(ts=time.time(), username="", nickname=line_nickname, text=text)
                    )

        session_info = {
            "connection_id": connection_id,
            "user_id": current_user.id,
            "username": current_user.username,
            "nickname": nickname,
            "role": role,
            "room_code": room.room_code,
            "file_id": room.file_id,
            "meeting_name": room.meeting_name,
            "transcriber": None,
            "tingwu_started": False,
            "tingwu_failed": False,
            "is_recording": False,
        }
        tingwu_lock = asyncio.Lock()

        async def on_tingwu_result(display_text, total_text, is_sentence_end, speaker_id=None, speaker_label=None):
            body = _strip_speaker_prefix(display_text)
            if not body and not is_sentence_end:
                return
            if is_sentence_end and body:
                merged = await room_manager.append_transcript(
                    room.room_code, current_user.username, nickname, body
                )
                collab_svc.append_transcript(db, room, f"[{nickname}] {body}")
                await room_manager.broadcast(room.room_code, {
                    "type": "transcript_update",
                    "merged_transcript": merged,
                    "speaker": nickname,
                    "text": body,
                    "is_partial": False,
                })
            elif body:
                await manager.send_json(connection_id, {
                    "type": "result",
                    "text": body,
                    "speaker_label": nickname,
                    "is_partial": True,
                    "timestamp": datetime.now().isoformat(),
                })

        async def on_tingwu_error(msg: str):
            session_info["tingwu_failed"] = True
            await manager.send_json(connection_id, {"type": "error", "message": "实时转写失败，请稍后重试"})

        async def ensure_tingwu() -> None:
            if session_info["role"] == "viewer":
                return
            if session_info["tingwu_started"] or session_info["tingwu_failed"]:
                return
            rt = room_manager.get_room(room.room_code)
            if (
                rt
                and rt.active_recorder_count() >= collab_max_recorders
                and not session_info["is_recording"]
            ):
                raise ValueError(f"同时录音人数已达上限（{collab_max_recorders}）")
            async with tingwu_lock:
                if session_info["tingwu_started"]:
                    return
                transcriber = tingwu_engine.create_streaming_session(
                    on_result=on_tingwu_result, on_error=on_tingwu_error
                )
                session_info["transcriber"] = transcriber
                await tingwu_engine.start_session_async(transcriber)
                await tingwu_engine.send_keepalive_async(transcriber)
                session_info["tingwu_started"] = True
                await manager.send_json(connection_id, {"type": "tingwu_ready"})

        state = await room_manager.room_state_payload(room.room_code)
        await manager.send_json(connection_id, state)
        await room_manager.broadcast(
            room.room_code,
            {
                "type": "participant_event",
                "event": "join",
                "username": current_user.username,
                "nickname": nickname,
                "role": role,
            },
            exclude=connection_id,
        )
        await room_manager.broadcast(room.room_code, await room_manager.room_state_payload(room.room_code))

        while True:
            raw = await websocket.receive()
            if raw.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect()

            if "bytes" in raw:
                if session_info["role"] == "viewer" or not session_info["is_recording"]:
                    continue
                audio = raw["bytes"]
                if not audio or session_info.get("tingwu_failed"):
                    continue
                await ensure_tingwu()
                await tingwu_engine.feed_stream_async(session_info["transcriber"], audio, 16000)
                continue

            if "text" not in raw:
                continue
            message = json.loads(raw["text"])

            if message.get("type") == "record_start":
                if session_info["role"] == "viewer":
                    await manager.send_json(connection_id, {"type": "error", "message": "观看者无法录音"})
                    continue
                db_room = collab_svc.get_room_by_code(db, room.room_code)
                if db_room.status not in ("waiting", "live"):
                    await manager.send_json(connection_id, {"type": "error", "message": "会议未进行中"})
                    continue
                try:
                    await ensure_tingwu()
                    session_info["is_recording"] = True
                    await room_manager.set_recording(room.room_code, current_user.username, True)
                    await room_manager.broadcast(room.room_code, {
                        "type": "participant_event",
                        "event": "recording_start",
                        "username": current_user.username,
                    })
                except ValueError as exc:
                    await manager.send_json(connection_id, {"type": "error", "message": str(exc)})
                continue

            if message.get("type") == "record_stop":
                session_info["is_recording"] = False
                await room_manager.set_recording(room.room_code, current_user.username, False)
                if session_info["tingwu_started"] and session_info["transcriber"]:
                    await tingwu_engine.finalize_stream_async(session_info["transcriber"])
                    session_info["tingwu_started"] = False
                    session_info["transcriber"] = None
                continue

            if message.get("type") == "end_meeting":
                if current_user.username != room.host_username:
                    await manager.send_json(connection_id, {"type": "error", "message": "仅主持人可结束会议"})
                    continue
                await finalize_collaborative_room(db, room, host_connection_id=connection_id)
                return

            if message.get("type") == "leave":
                break

    except WebSocketDisconnect:
        pass
    finally:
        code = room_manager.unregister_connection(connection_id)
        if code and session_info:
            await room_manager.broadcast(code, {
                "type": "participant_event",
                "event": "leave",
                "username": session_info.get("username"),
            })
            await room_manager.broadcast(code, await room_manager.room_state_payload(code))
        if session_info:
            transcriber = session_info.get("transcriber")
            if transcriber and session_info.get("tingwu_started"):
                try:
                    await tingwu_engine.finalize_stream_async(transcriber)
                except Exception:
                    pass
        db.close()
        manager.disconnect(connection_id)


async def finalize_collaborative_room(
    db,
    room,
    host_connection_id: str = "",
    start_time: float | None = None,
) -> None:
    """合并转写、生成速览并写入 meetings 表；REST 与 WS end_meeting 共用。"""
    if start_time is None:
        start_time = time.time()

    room = db.query(CollaborativeRoom).filter(CollaborativeRoom.id == room.id).first()
    if not room:
        return
    if room.status == "completed":
        return

    if room.status not in ("ending", "completed"):
        collab_svc.end_room(db, room, room.host_username)
        room = db.query(CollaborativeRoom).filter(CollaborativeRoom.id == room.id).first()

    rt = room_manager.get_room(room.room_code)
    merged = rt.merged_text() if rt else (room.merged_transcript or "")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(
        c for c in room.meeting_name if c.isalnum() or c in (" ", "-", "_")
    ).strip().replace(" ", "_")
    transcript_filename = f"{safe_name}_{room.file_id}_{timestamp}_realtime.txt"
    summary_filename = f"{safe_name}_{room.file_id}_{timestamp}_realtime.md"
    transcript_path = os.path.join(output_dir, "transcripts", transcript_filename)

    await run_io(Path(transcript_path).write_text, merged, encoding="utf-8")
    await room_manager.broadcast(room.room_code, {
        "type": "generating_transcript",
        "message": "正在整理转写并生成速览...",
    })

    collab_svc.complete_room(db, room, merged)

    await room_manager.broadcast(room.room_code, {
        "type": "transcribe_complete",
        "total_text": merged,
        "file_id": room.file_id,
    })
    await room_manager.broadcast(room.room_code, {
        "type": "generating_summary",
        "file_id": room.file_id,
        "message": "正在生成文字与图文速览...",
    })

    summary = ""
    summary_visual_dict = None
    dual = None
    try:
        dual = await _run_with_keepalive(
            host_connection_id,
            generate_dual_summaries(get_glm_client(), merged, room.meeting_name),
            stage="summary",
        )
        if dual and dual.markdown:
            summary = dual.markdown
            summary_visual_dict = visual_dict_from_result(dual)
            summary_path = os.path.join(output_dir, "summaries", summary_filename)
            await run_io(Path(summary_path).write_text, summary, encoding="utf-8")
            if dual.visual_json:
                visual_path = summary_path.replace(".md", "_visual.json")
                await run_io(Path(visual_path).write_text, dual.visual_json, encoding="utf-8")
    except Exception as exc:
        logger.error(f"协作会议速览生成失败: {exc}", exc_info=True)

    total_duration_ms = (time.time() - start_time) * 1000
    meeting_data = {
        "file_id": room.file_id,
        "user_id": room.host_user_id,
        "meeting_name": room.meeting_name,
        "original_filename": transcript_filename,
        "meeting_type": "realtime",
        "audio_file_path": None,
        "transcript_file_path": transcript_path,
        "summary_file_path": os.path.join(output_dir, "summaries", summary_filename) if summary else None,
        "transcript": merged,
        "summary": summary,
        "summary_visual": dual.visual_json if dual else None,
        "summary_visual_status": dual.visual_status if dual else None,
        "transcript_length": len(merged),
        "summary_length": len(summary) if summary else 0,
        "total_duration_ms": round(total_duration_ms, 2),
        "status": "completed" if summary else "failed",
        "is_collaborative": True,
        "room_code": room.room_code,
        "host_username": room.host_username,
    }
    await save_meeting_to_db_async(meeting_data)

    await room_manager.broadcast(room.room_code, {
        "type": "session_end",
        "file_id": room.file_id,
        "total_text": merged,
        "summary": summary,
        "summary_visual": summary_visual_dict,
        "summary_visual_status": dual.visual_status if dual else None,
    })
    room_manager.remove_room(room.room_code)
