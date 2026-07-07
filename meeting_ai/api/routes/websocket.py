import json
import re
import uuid
import os
import time
import asyncio
from contextlib import suppress
from pathlib import Path
from datetime import datetime

_FILE_ID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def _extract_file_id_from_filename(filename: str) -> str | None:
    match = _FILE_ID_RE.search(filename)
    return match.group(0) if match else None


def _find_transcript_by_file_id(transcripts_dir: str, file_id: str) -> tuple[str | None, str | None]:
    if not os.path.exists(transcripts_dir):
        return None, None
    for filename in os.listdir(transcripts_dir):
        if not filename.endswith(".txt"):
            continue
        if filename.startswith(file_id) or f"_{file_id}_" in filename:
            return os.path.join(transcripts_dir, filename), filename
    return None, None
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, HTTPException, Body
from pydantic import BaseModel, Field
from api.auth_utils import get_user_from_token, get_current_user
from db.models import User
from db.session import SessionFactory
from utils.logger import get_logger
from utils.meeting_name import resolve_meeting_name, safe_filename_prefix
from asr.tingwu_realtime import (
    TINGWU_KEEPALIVE_INTERVAL_SECONDS,
    TingwuRealtimeEngine,
    TingwuTaskError,
)
from llm.client_holder import get_llm_client
from llm.summary_service import generate_dual_summaries, visual_dict_from_result
from config.config import output_dir
from db.session import save_meeting_to_db_async
from utils.executors import run_io

router = APIRouter()
logger = get_logger("websocket_route")

# 实时转写使用通义听悟；批量上传仍使用 FunASR（见 meeting.py）
tingwu_engine = TingwuRealtimeEngine()


class ConnectionManager:
    """管理 WebSocket 连接"""
    
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, connection_id: str):
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        logger.info(f"WebSocket 连接建立", extra={'request_id': connection_id, 'output_params': {'connection_id': connection_id}})
    
    def disconnect(self, connection_id: str):
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
            logger.info(f"WebSocket 连接断开", extra={'request_id': connection_id})
    
    async def send_json(self, connection_id: str, data: dict) -> bool:
        ws = self.active_connections.get(connection_id)
        if ws is None:
            return False
        try:
            await ws.send_json(data)
            return True
        except (WebSocketDisconnect, RuntimeError) as e:
            logger.warning(
                f"WebSocket 发送失败: {type(e).__name__}: {e}",
                extra={
                    "request_id": connection_id,
                    "msg_type": data.get("type"),
                    "output_params": {"error_type": type(e).__name__, "error": str(e)},
                },
            )
            self.disconnect(connection_id)
            return False
        except Exception as e:
            logger.warning(
                f"WebSocket 发送异常: {e}",
                extra={
                    "request_id": connection_id,
                    "msg_type": data.get("type"),
                    "output_params": {"error_type": type(e).__name__, "error": str(e)},
                },
            )
            self.disconnect(connection_id)
            return False


manager = ConnectionManager()


WS_CLIENT_HEARTBEAT_INTERVAL_SECONDS = 15.0
RECENT_SESSION_TTL_SECONDS = 600.0
_recent_disconnect_sessions: dict[str, dict[str, Any]] = {}


def _classify_ws_close_code(code: int | None) -> str:
    if code is None:
        return "unknown"
    labels = {
        1000: "normal_closure",
        1001: "going_away",
        1002: "protocol_error",
        1003: "unsupported_data",
        1005: "no_status_received",
        1006: "abnormal_closure_no_close_frame",
        1007: "invalid_frame_payload",
        1008: "policy_violation",
        1009: "message_too_big",
        1011: "server_error",
        1012: "service_restart",
        1013: "try_again_later",
        1014: "bad_gateway",
        1015: "tls_handshake_failure",
        4001: "auth_failed",
    }
    return labels.get(code, f"code_{code}")


def _seconds_since(timestamp: float | None) -> float | None:
    if timestamp is None:
        return None
    return round(time.time() - timestamp, 2)


def _build_ws_diagnostics(
    session_info: dict,
    connection_id: str,
    start_time: float,
    **extra: Any,
) -> dict[str, Any]:
    transcriber = session_info.get("transcriber")
    diagnostics: dict[str, Any] = {
        "connection_id": connection_id,
        "user_id": session_info.get("user_id"),
        "duration_ms": round((time.time() - start_time) * 1000, 2),
        "heartbeat_stage": session_info.get("heartbeat_stage"),
        "audio_chunks": session_info.get("audio_chunks", 0),
        "total_text_length": len(session_info.get("total_text") or ""),
        "tingwu_started": bool(session_info.get("tingwu_started")),
        "tingwu_finalized": bool(session_info.get("tingwu_finalized")),
        "tingwu_failed": bool(session_info.get("tingwu_failed")),
        "tingwu_closed": getattr(transcriber, "_closed", None) if transcriber else None,
        "tingwu_task_id": getattr(transcriber, "task_id", None) if transcriber else None,
        "saved": bool(session_info.get("saved")),
        "meeting_name": session_info.get("meeting_name"),
        "client_ping_count": session_info.get("client_ping_count", 0),
        "outbound_heartbeat_count": session_info.get("outbound_heartbeat_count", 0),
        "seconds_since_client_ping": _seconds_since(session_info.get("last_client_ping_at")),
        "seconds_since_client_audio": _seconds_since(session_info.get("last_client_audio_at")),
        "seconds_since_outbound_heartbeat": _seconds_since(session_info.get("last_outbound_heartbeat_at")),
        "seconds_since_tingwu_keepalive": _seconds_since(session_info.get("last_tingwu_keepalive_at")),
        "disconnect_code": session_info.get("disconnect_code"),
        "disconnect_reason": session_info.get("disconnect_reason") or "",
        "disconnect_code_label": _classify_ws_close_code(session_info.get("disconnect_code")),
        "client_report_received": bool(session_info.get("client_report_received")),
        "normal_end": bool(session_info.get("normal_end")),
    }
    diagnostics.update(extra)
    return diagnostics


def _archive_session_diagnostics(
    connection_id: str,
    session_info: dict,
    start_time: float,
    **extra: Any,
) -> None:
    now = time.time()
    stale_ids = [
        cid
        for cid, item in _recent_disconnect_sessions.items()
        if now - item.get("archived_at", 0) > RECENT_SESSION_TTL_SECONDS
    ]
    for cid in stale_ids:
        _recent_disconnect_sessions.pop(cid, None)
    _recent_disconnect_sessions[connection_id] = {
        "archived_at": now,
        "diagnostics": _build_ws_diagnostics(session_info, connection_id, start_time, **extra),
    }


def _log_ws_disconnect(
    connection_id: str,
    session_info: dict,
    start_time: float,
    event: str,
    *,
    level: str = "info",
    **extra: Any,
) -> None:
    diagnostics = _build_ws_diagnostics(session_info, connection_id, start_time, **extra)
    log_fn = logger.warning if level == "warning" else logger.info
    log_fn(event, extra={"request_id": connection_id, "output_params": diagnostics})


class WsDisconnectReport(BaseModel):
    connection_id: str | None = None
    close_code: int | None = None
    close_reason: str | None = None
    was_clean: bool | None = None
    duration_ms: float | None = None
    is_recording: bool = False
    visibility_state: str | None = None
    embedded: bool = False
    portal_host: bool = False
    last_pong_age_ms: float | None = None
    last_ping_sent_age_ms: float | None = None
    last_audio_sent_age_ms: float | None = None
    client_ping_count: int = 0
    audio_flush_count: int = 0
    ws_url_host: str | None = None
    user_agent: str | None = None
    disconnect_source: str = "client_onclose"
    session_outcome: str | None = None
    user_stop_requested: bool = False
    session_completed: bool = False
    page_load_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


def _is_normal_disconnect_report(
    report: WsDisconnectReport,
    server_diag: dict[str, Any] | None,
) -> bool:
    if report.session_outcome in ("normal_end", "user_stop_summary"):
        return True
    if report.extra.get("session_outcome") in ("normal_end", "user_stop_summary"):
        return True
    if report.session_completed or report.user_stop_requested:
        if server_diag and server_diag.get("saved"):
            return True
    if server_diag and server_diag.get("saved") and server_diag.get("normal_end"):
        return True
    return False


async def _tingwu_periodic_keepalive(session_info: dict, connection_id: str) -> None:
    """听悟侧定期发送静音，避免 10s 无数据触发 IDLE_TIMEOUT。"""
    try:
        while session_info.get("tingwu_started") and not session_info.get("saved"):
            if session_info.get("tingwu_failed"):
                break
            transcriber_ref = session_info.get("transcriber")
            if transcriber_ref is None or getattr(transcriber_ref, "_closed", False):
                break
            await tingwu_engine.send_keepalive_async(transcriber_ref)
            session_info["last_tingwu_keepalive_at"] = time.time()
            await asyncio.sleep(TINGWU_KEEPALIVE_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning(
            f"听悟保活失败: {e}",
            extra={"request_id": connection_id},
        )


async def _websocket_outbound_heartbeat(session_info: dict, connection_id: str) -> None:
    """定期向客户端推送心跳，避免代理/浏览器在后台长时间无下行数据时断开 WebSocket。"""
    try:
        while not session_info.get("saved"):
            await asyncio.sleep(WS_CLIENT_HEARTBEAT_INTERVAL_SECONDS)
            if session_info.get("saved"):
                break
            session_info["last_outbound_heartbeat_at"] = time.time()
            session_info["outbound_heartbeat_count"] = session_info.get("outbound_heartbeat_count", 0) + 1
            await manager.send_json(
                connection_id,
                {"type": "heartbeat", "stage": session_info.get("heartbeat_stage", "recording")},
            )
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning(
            f"WebSocket 下行心跳失败: {e}",
            extra={"request_id": connection_id},
        )


def _start_ws_heartbeat_task(session_info: dict, connection_id: str) -> None:
    task = session_info.get("ws_heartbeat_task")
    if task is not None and not task.done():
        return
    session_info["ws_heartbeat_task"] = asyncio.create_task(
        _websocket_outbound_heartbeat(session_info, connection_id)
    )


async def _cancel_ws_heartbeat_task(session_info: dict) -> None:
    task = session_info.get("ws_heartbeat_task")
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def _handle_inbound_while_busy(
    raw_message: dict,
    connection_id: str,
    session_info: dict,
) -> None:
    """长任务期间处理客户端 ping；其他消息在长任务结束后由主循环继续处理。"""
    if raw_message.get("type") == "websocket.disconnect":
        session_info["disconnect_code"] = raw_message.get("code")
        session_info["disconnect_reason"] = raw_message.get("reason") or ""
        raise WebSocketDisconnect(
            code=raw_message.get("code", 1000),
            reason=raw_message.get("reason") or "",
        )

    if "text" not in raw_message:
        return

    try:
        message = json.loads(raw_message["text"])
    except json.JSONDecodeError:
        return

    if message.get("type") == "ping":
        session_info["last_client_ping_at"] = time.time()
        session_info["client_ping_count"] = session_info.get("client_ping_count", 0) + 1
        await manager.send_json(connection_id, {"type": "pong"})


async def _run_with_ping_drain(
    websocket: WebSocket,
    connection_id: str,
    session_info: dict,
    coro,
    *,
    stage: str = "summary",
    interval: float = 12.0,
):
    """长任务期间继续响应 ping 并下发心跳，避免 cpolar/代理因服务端阻塞而断开。"""
    task = asyncio.create_task(coro)
    try:
        while not task.done():
            recv_task = asyncio.create_task(websocket.receive())
            done, pending = await asyncio.wait(
                {task, recv_task},
                timeout=interval,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                recv_task.cancel()
                with suppress(asyncio.CancelledError):
                    await recv_task
                await manager.send_json(
                    connection_id,
                    {"type": "heartbeat", "stage": stage},
                )
                continue

            if task in done:
                recv_task.cancel()
                with suppress(asyncio.CancelledError):
                    await recv_task
                break

            raw_message = recv_task.result()
            await _handle_inbound_while_busy(raw_message, connection_id, session_info)
    except WebSocketDisconnect:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        raise

    return await task


async def _run_with_keepalive(
    connection_id: str,
    coro,
    stage: str = "summary",
    interval: float = 12.0,
):
    """长任务期间定期发送心跳，避免代理/浏览器因空闲断开连接。"""
    task = asyncio.create_task(coro)
    while not task.done():
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=interval)
        except asyncio.TimeoutError:
            await manager.send_json(
                connection_id,
                {"type": "heartbeat", "stage": stage},
            )
    return await task


async def _persist_realtime_session_emergency(
    session_info: dict,
    connection_id: str,
    start_time: float,
    *,
    reason: str = "interrupted",
) -> str | None:
    """WebSocket 异常断开时保存转写，避免长时间录音数据丢失。"""
    if session_info.get("saved"):
        return session_info.get("file_id")

    user_meeting_name = (session_info.get("meeting_name") or "").strip()

    transcriber = session_info.get("transcriber")
    if transcriber is not None:
        session_info["total_text"] = transcriber.total_text()

    total_text = (session_info.get("total_text") or "").strip()
    if session_info.get("audio_chunks", 0) <= 0 and not total_text:
        return None

    file_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_info["file_id"] = file_id
    session_info["saved"] = True

    meeting_name = resolve_meeting_name(
        user_meeting_name or None,
        at=session_info.get("start_time"),
    )

    safe_name = safe_filename_prefix(user_meeting_name or None).rstrip("_")
    transcript_filename = (
        f"{safe_name}_{file_id}_{timestamp}_realtime.txt"
        if safe_name
        else f"{file_id}_{timestamp}_realtime.txt"
    )
    transcript_path = os.path.join(output_dir, "transcripts", transcript_filename)
    await run_io(Path(transcript_path).write_text, total_text, encoding="utf-8")

    total_duration_ms = (time.time() - start_time) * 1000
    meeting_data = {
        "file_id": file_id,
        "user_id": session_info["user_id"],
        "meeting_name": meeting_name,
        "original_filename": transcript_filename,
        "meeting_type": "realtime",
        "audio_file_path": None,
        "transcript_file_path": transcript_path,
        "summary_file_path": None,
        "transcript": total_text,
        "summary": None,
        "transcript_length": len(total_text),
        "summary_length": 0,
        "total_duration_ms": round(total_duration_ms, 2),
        "status": reason,
        "error_message": "连接中断，已自动保存转写内容" if reason == "interrupted" else None,
    }
    await save_meeting_to_db_async(meeting_data)
    logger.info(
        "实时会议已自动保存（连接中断）",
        extra={
            "request_id": connection_id,
            "output_params": {
                "file_id": file_id,
                "reason": reason,
                "text_length": len(total_text),
                "audio_chunks": session_info.get("audio_chunks", 0),
            },
        },
    )
    return file_id


@router.websocket("/ws/transcribe")
async def websocket_transcribe(
    websocket: WebSocket,
    token: str = Query(default=""),
    room_code: str = Query(default=""),
):
    """
    WebSocket 实时语音转文本
    客户端发送音频数据块，服务端返回识别结果
    """
    db = SessionFactory()
    try:
        current_user = get_user_from_token(token, db)
    finally:
        db.close()

    if not current_user:
        await websocket.accept()
        await websocket.close(code=4001, reason="请先登录")
        return

    start_time = time.time()
    connection_id = str(uuid.uuid4())
    await manager.connect(websocket, connection_id)

    if room_code.strip():
        from api.collaborative_ws import handle_collaborative_ws

        await handle_collaborative_ws(
            websocket, connection_id, current_user, room_code.strip(), start_time
        )
        return

    session_info = {
        "connection_id": connection_id,
        "user_id": current_user.id,
        "start_time": datetime.now().isoformat(),
        "total_text": "",
        "file_id": None,
        "meeting_name": None,
        "audio_chunks": 0,
        "transcriber": None,
        "tingwu_failed": False,
        "tingwu_started": False,
        "tingwu_finalized": False,
        "saved": False,
        "tingwu_keepalive_task": None,
        "ws_heartbeat_task": None,
        "heartbeat_stage": "recording",
        "last_client_ping_at": None,
        "last_client_audio_at": None,
        "last_outbound_heartbeat_at": None,
        "last_tingwu_keepalive_at": None,
        "client_ping_count": 0,
        "outbound_heartbeat_count": 0,
        "disconnect_code": None,
        "disconnect_reason": "",
        "client_report_received": False,
    }
    tingwu_start_lock = asyncio.Lock()
    _start_ws_heartbeat_task(session_info, connection_id)
    await manager.send_json(connection_id, {
        "type": "session_info",
        "connection_id": connection_id,
    })

    async def on_tingwu_result(
        display_text: str,
        total_text: str,
        is_sentence_end: bool,
        speaker_id: str | None = None,
        speaker_label: str | None = None,
    ):
        if is_sentence_end:
            session_info["total_text"] = total_text
        payload = {
            "type": "result",
            "text": display_text,
            "total_text": session_info["total_text"],
            "is_partial": not is_sentence_end,
            "timestamp": datetime.now().isoformat(),
        }
        if speaker_id is not None:
            payload["speaker_id"] = speaker_id
        if speaker_label:
            payload["speaker_label"] = speaker_label
        await manager.send_json(connection_id, payload)

    async def on_tingwu_error(error_message: str):
        session_info["tingwu_failed"] = True
        await manager.send_json(connection_id, {
            "type": "error",
            "message": "实时转写失败，请稍后重试",
        })

    transcriber = tingwu_engine.create_streaming_session(
        on_result=on_tingwu_result,
        on_error=on_tingwu_error,
    )
    session_info["transcriber"] = transcriber

    async def ensure_tingwu_started() -> None:
        """在用户开始录音后再连接听悟，避免 StartTranscription 后长时间无音频触发 IDLE_TIMEOUT。"""
        if session_info.get("tingwu_failed"):
            return
        if session_info["tingwu_started"]:
            await manager.send_json(connection_id, {
                "type": "tingwu_ready",
                "message": "转写通道已就绪",
            })
            return
        async with tingwu_start_lock:
            if session_info["tingwu_started"] or session_info.get("tingwu_failed"):
                if session_info["tingwu_started"]:
                    await manager.send_json(connection_id, {
                        "type": "tingwu_ready",
                        "message": "转写通道已就绪",
                    })
                return
            await tingwu_engine.start_session_async(transcriber)
            await tingwu_engine.send_keepalive_async(transcriber)
            session_info["tingwu_started"] = True
            if session_info.get("tingwu_keepalive_task") is None:
                session_info["tingwu_keepalive_task"] = asyncio.create_task(
                    _tingwu_periodic_keepalive(session_info, connection_id)
                )
            logger.info(
                "听悟推流已启动",
                extra={"request_id": connection_id, "output_params": {"task_id": transcriber.task_id}},
            )
            await manager.send_json(connection_id, {
                "type": "tingwu_ready",
                "message": "转写通道已就绪",
            })

    try:
        logger.info(
            "实时转写 WebSocket 已连接，等待开始录音",
            extra={"request_id": connection_id},
        )
        while True:
            # 控制消息：JSON 文本帧；音频：二进制 PCM 帧（16kHz int16）
            try:
                raw_message = await asyncio.wait_for(
                    websocket.receive(), timeout=WS_CLIENT_HEARTBEAT_INTERVAL_SECONDS + 5.0
                )
            except asyncio.TimeoutError:
                await manager.send_json(
                    connection_id,
                    {"type": "heartbeat", "stage": "recording"},
                )
                continue

            if raw_message.get("type") == "websocket.disconnect":
                session_info["disconnect_code"] = raw_message.get("code")
                session_info["disconnect_reason"] = raw_message.get("reason") or ""
                raise WebSocketDisconnect(
                    code=raw_message.get("code", 1000),
                    reason=raw_message.get("reason") or "",
                )

            if "bytes" in raw_message:
                audio_bytes = raw_message["bytes"]
                if not audio_bytes:
                    continue
                if session_info.get("tingwu_failed"):
                    continue
                await ensure_tingwu_started()
                session_info["audio_chunks"] += 1
                session_info["last_client_audio_at"] = time.time()
                await tingwu_engine.feed_stream_async(
                    session_info["transcriber"], audio_bytes, 16000
                )
                session_info["total_text"] = session_info["transcriber"].total_text()
                continue

            if "text" not in raw_message:
                continue

            try:
                message = json.loads(raw_message["text"])
                
                # 处理初始化消息（会议名称）
                if message.get("type") == "init":
                    meeting_name = (message.get("meeting_name") or "").strip()
                    session_info["meeting_name"] = meeting_name or None
                    logger.info(
                        f"设置会议名称",
                        extra={
                            'request_id': connection_id,
                            'input_params': {
                                'meeting_name': meeting_name or '(未填写，将自动生成)',
                            },
                        },
                    )
                    continue

                if message.get("type") == "ping":
                    session_info["last_client_ping_at"] = time.time()
                    session_info["client_ping_count"] = session_info.get("client_ping_count", 0) + 1
                    await manager.send_json(connection_id, {"type": "pong"})
                    continue

                if message.get("type") == "record_start":
                    mn = (message.get("meeting_name") or "").strip()
                    if mn:
                        session_info["meeting_name"] = mn
                    await ensure_tingwu_started()
                    continue

                # 兼容旧版 JSON 音频帧（建议客户端改用二进制 PCM）
                if message.get("type") == "audio":
                    if session_info.get("tingwu_failed"):
                        continue
                    await ensure_tingwu_started()
                    audio_bytes = bytes(message.get("data", []))
                    sample_rate = message.get("sample_rate", 16000)
                    session_info["audio_chunks"] += 1
                    session_info["last_client_audio_at"] = time.time()
                    await tingwu_engine.feed_stream_async(
                        session_info["transcriber"], audio_bytes, sample_rate
                    )
                    session_info["total_text"] = session_info["transcriber"].total_text()

                elif message.get("type") == "end":
                    if session_info["tingwu_started"]:
                        await manager.send_json(connection_id, {
                            "type": "generating_transcript",
                            "message": "正在整理说话人分离转写，请稍候...",
                        })
                        await _run_with_ping_drain(
                            websocket,
                            connection_id,
                            session_info,
                            tingwu_engine.finalize_stream_async(session_info["transcriber"]),
                            stage="transcript",
                        )
                        session_info["tingwu_finalized"] = True
                        session_info["total_text"] = session_info["transcriber"].total_text()

                    # 会话结束，生成 AI 总结
                    duration_ms = (time.time() - start_time) * 1000
                    logger.info(f"会话结束，开始生成 AI 总结", extra={'request_id': connection_id, 'output_params': {'duration_ms': round(duration_ms, 2), 'total_text_length': len(session_info["total_text"]), 'audio_chunks': session_info["audio_chunks"]}})
                    
                    # 保存转写文本
                    file_id = str(uuid.uuid4())
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    session_info["file_id"] = file_id
                    
                    # 构建文件名（用户填写名称时加入前缀）
                    user_meeting_name = (session_info.get("meeting_name") or "").strip()
                    safe_name = safe_filename_prefix(user_meeting_name or None).rstrip("_")
                    transcript_filename = (
                        f"{safe_name}_{file_id}_{timestamp}_realtime.txt"
                        if safe_name
                        else f"{file_id}_{timestamp}_realtime.txt"
                    )
                    summary_filename = transcript_filename.replace(".txt", ".md")
                    
                    # 异步保存转写文本
                    transcript_path = os.path.join(
                        output_dir, "transcripts",
                        transcript_filename
                    )
                    await run_io(Path(transcript_path).write_text, session_info["total_text"], encoding='utf-8')
                    logger.info(f"实时转写文本已保存", extra={'request_id': connection_id, 'output_params': {'transcript_file': transcript_path, 'text_length': len(session_info["total_text"])}})

                    end_result_base = {
                        "total_text": session_info["total_text"],
                        "file_id": file_id,
                        "transcript_file": transcript_path,
                        "duration": str(
                            datetime.now()
                            - datetime.fromisoformat(session_info["start_time"])
                        ),
                    }

                    # 先推送转写完成，前端可立即展示全文
                    await manager.send_json(connection_id, {
                        "type": "transcribe_complete",
                        **end_result_base,
                    })
                    session_info["heartbeat_stage"] = "summary"
                    await manager.send_json(connection_id, {
                        "type": "generating_summary",
                        "message": "正在生成文字与图文速览...",
                        "file_id": file_id,
                    })

                    # 并行生成 Markdown + 图文速览（期间发送心跳保活）
                    try:
                        dual = await _run_with_ping_drain(
                            websocket,
                            connection_id,
                            session_info,
                            generate_dual_summaries(
                                get_llm_client(),
                                session_info["total_text"],
                                user_meeting_name or None,
                                session_info.get("start_time"),
                            ),
                            stage="summary",
                        )
                        if dual.markdown_error or not dual.markdown:
                            raise RuntimeError(dual.markdown_error or 'Markdown 速览生成失败')

                        summary = dual.markdown
                        summary_visual_dict = visual_dict_from_result(dual)
                        visual_title = (
                            summary_visual_dict.get("title")
                            if isinstance(summary_visual_dict, dict)
                            else None
                        )
                        meeting_name = resolve_meeting_name(
                            user_meeting_name or None,
                            summary=summary,
                            visual_title=visual_title,
                            at=session_info.get("start_time"),
                        )

                        summary_path = os.path.join(
                            output_dir, "summaries", summary_filename
                        )
                        await run_io(Path(summary_path).write_text, summary, encoding='utf-8')
                        visual_path = summary_path.replace('.md', '_visual.json')
                        if dual.visual_json:
                            await run_io(Path(visual_path).write_text, dual.visual_json, encoding='utf-8')

                        total_duration_ms = (time.time() - start_time) * 1000
                        logger.info(
                            "实时会议纪要已保存",
                            extra={
                                "request_id": connection_id,
                                "output_params": {
                                    "summary_file": summary_path,
                                    "summary_length": len(summary),
                                    "total_duration_ms": round(total_duration_ms, 2),
                                },
                            },
                        )

                        # 保存到数据库
                        try:
                            meeting_data = {
                                'file_id': file_id,
                                'user_id': session_info["user_id"],
                                'meeting_name': meeting_name,
                                'original_filename': transcript_filename,
                                'meeting_type': 'realtime',
                                'audio_file_path': None,
                                'transcript_file_path': transcript_path,
                                'summary_file_path': summary_path,
                                'transcript': session_info["total_text"],
                                'summary': summary,
                                'summary_visual': dual.visual_json,
                                'summary_visual_status': dual.visual_status,
                                'transcript_length': len(session_info["total_text"]),
                                'summary_length': len(summary),
                                'total_duration_ms': round(total_duration_ms, 2),
                                'status': 'completed',
                            }
                            await save_meeting_to_db_async(meeting_data)
                            session_info["saved"] = True
                            logger.info(f"实时会议数据已保存到数据库", extra={'request_id': connection_id})
                        except Exception as db_error:
                            logger.error(f"保存实时会议数据到数据库失败: {str(db_error)}", exc_info=True, extra={'request_id': connection_id})

                        end_result = {
                            "type": "session_end",
                            "meeting_name": meeting_name,
                            "summary": summary,
                            "summary_visual": summary_visual_dict,
                            "summary_visual_status": dual.visual_status,
                            "summary_visual_error": dual.visual_error,
                            "summary_file": summary_path,
                            **end_result_base,
                        }
                        session_info["normal_end"] = True
                        session_info["disconnect_code"] = 1000
                        session_info["disconnect_reason"] = "session_end"
                        sent = await manager.send_json(connection_id, end_result)
                        if not sent:
                            logger.warning(
                                "session_end 推送失败，客户端可能已断开，结果已保存至文件",
                                extra={
                                    "request_id": connection_id,
                                    "file_id": file_id,
                                },
                            )

                    except Exception as e:
                        total_duration_ms = (time.time() - start_time) * 1000
                        logger.error(
                            "生成 AI 总结失败",
                            exc_info=True,
                            extra={
                                "request_id": connection_id,
                                "output_params": {
                                    "error": str(e),
                                    "error_type": type(e).__name__,
                                    "duration_ms": round(total_duration_ms, 2),
                                },
                            },
                        )
                        
                        # 即使AI总结失败，也保存转写文本到数据库
                        try:
                            fallback_name = resolve_meeting_name(
                                user_meeting_name or None,
                                at=session_info.get("start_time"),
                            )
                            meeting_data = {
                                'file_id': file_id,
                                'user_id': session_info["user_id"],
                                'meeting_name': fallback_name,
                                'original_filename': transcript_filename,
                                'meeting_type': 'realtime',
                                'audio_file_path': None,
                                'transcript_file_path': transcript_path,
                                'summary_file_path': None,
                                'transcript': session_info["total_text"],
                                'summary': None,
                                'transcript_length': len(session_info["total_text"]),
                                'summary_length': 0,
                                'total_duration_ms': round(total_duration_ms, 2),
                                'status': 'failed',
                                'error_message': f"生成总结失败: {str(e)}",
                            }
                            await save_meeting_to_db_async(meeting_data)
                            session_info["saved"] = True
                            logger.info(f"失败的实时会议数据已保存到数据库", extra={'request_id': connection_id})
                        except Exception as db_error:
                            logger.error(f"保存失败的实时会议数据到数据库失败: {str(db_error)}", exc_info=True, extra={'request_id': connection_id})
                        
                        end_result = {
                            "type": "session_end",
                            "meeting_name": fallback_name,
                            "summary": None,
                            "error": "会议纪要生成失败，请稍后重试",
                            **end_result_base,
                        }
                        session_info["normal_end"] = True
                        session_info["disconnect_code"] = 1000
                        session_info["disconnect_reason"] = "session_end"
                        await manager.send_json(connection_id, end_result)

                    break
                    
            except json.JSONDecodeError:
                logger.warning(
                    "无法解析 WebSocket 文本消息",
                    extra={"request_id": connection_id},
                )
    
    except WebSocketDisconnect as exc:
        session_info["disconnect_code"] = getattr(exc, "code", session_info.get("disconnect_code"))
        session_info["disconnect_reason"] = getattr(exc, "reason", None) or session_info.get("disconnect_reason") or ""
        disconnect_level = "info" if session_info.get("normal_end") or session_info.get("saved") else "warning"
        _log_ws_disconnect(
            connection_id,
            session_info,
            start_time,
            "WebSocket 断开连接",
            level=disconnect_level,
            disconnect_source="server_websocket_disconnect",
        )
    except RuntimeError as e:
        if "close message" in str(e).lower():
            _log_ws_disconnect(
                connection_id,
                session_info,
                start_time,
                "WebSocket 已关闭",
                disconnect_source="server_runtime_close",
            )
        else:
            raise
    except TingwuTaskError as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(
            f"听悟任务失败: {e}",
            extra={
                "request_id": connection_id,
                "output_params": {"duration_ms": round(duration_ms, 2)},
            },
        )
        await manager.send_json(connection_id, {
            "type": "error",
            "message": "实时转写失败，请稍后重试",
        })
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(
            f"WebSocket 错误",
            exc_info=True,
            extra={
                'request_id': connection_id,
                'output_params': _build_ws_diagnostics(
                    session_info,
                    connection_id,
                    start_time,
                    error=str(e),
                    error_type=type(e).__name__,
                    duration_ms=round(duration_ms, 2),
                ),
            },
        )
        if not getattr(session_info.get("transcriber"), "task_id", None):
            await manager.send_json(connection_id, {
                "type": "error",
                "message": "实时转写启动失败，请稍后重试",
            })
    finally:
        keepalive_task = session_info.get("tingwu_keepalive_task")
        if keepalive_task is not None and not keepalive_task.done():
            keepalive_task.cancel()
            try:
                await keepalive_task
            except asyncio.CancelledError:
                pass
        await _cancel_ws_heartbeat_task(session_info)

        transcriber = session_info.get("transcriber")
        if (
            transcriber is not None
            and session_info.get("tingwu_started")
            and not session_info.get("tingwu_finalized")
            and not session_info.get("tingwu_failed")
        ):
            try:
                await tingwu_engine.finalize_stream_async(transcriber)
                session_info["total_text"] = transcriber.total_text()
                session_info["tingwu_finalized"] = True
            except Exception as e:
                logger.warning(f"听悟会话收尾失败: {e}", extra={"request_id": connection_id})

        if not session_info.get("saved") and session_info.get("audio_chunks", 0) > 0:
            try:
                await _persist_realtime_session_emergency(
                    session_info,
                    connection_id,
                    start_time,
                    reason="interrupted",
                )
            except Exception as e:
                logger.error(
                    f"连接中断后自动保存失败: {e}",
                    exc_info=True,
                    extra={"request_id": connection_id},
                )

        manager.disconnect(connection_id)
        _archive_session_diagnostics(
            connection_id,
            session_info,
            start_time,
            cleanup_completed_at=datetime.now().isoformat(),
        )
        logger.info(
            f"会话清理完成",
            extra={
                'request_id': connection_id,
                'output_params': _build_ws_diagnostics(session_info, connection_id, start_time),
            },
        )


@router.post("/ws/disconnect-report")
async def ws_disconnect_report(
    report: WsDisconnectReport,
    current_user: User = Depends(get_current_user),
):
    """客户端 WebSocket 断开后上报诊断信息，便于定位 cpolar/网络/iframe 等原因。"""
    connection_id = (report.connection_id or "").strip() or "unknown"
    archived = _recent_disconnect_sessions.get(connection_id, {})
    server_diag = archived.get("diagnostics") if archived else None
    if archived and server_diag:
        server_diag["client_report_received"] = True
    close_label = _classify_ws_close_code(report.close_code)
    is_normal = _is_normal_disconnect_report(report, server_diag)
    log_fn = logger.info if is_normal else logger.warning
    log_message = (
        "WebSocket 客户端断开诊断上报（正常结束）"
        if is_normal
        else "WebSocket 客户端断开诊断上报"
    )

    log_fn(
        log_message,
        extra={
            "request_id": connection_id,
            "output_params": {
                "user_id": current_user.id,
                "username": current_user.username,
                "is_normal_end": is_normal,
                "client_report": report.model_dump(),
                "close_code_label": close_label,
                "server_diagnostics": server_diag,
                "server_report_lag_seconds": (
                    round(time.time() - archived.get("archived_at", time.time()), 2)
                    if archived else None
                ),
            },
        },
    )
    return {"success": True, "connection_id": connection_id}


@router.get("/ws/status")
async def websocket_status():
    """获取 WebSocket 连接状态"""
    return {
        "active_connections": len(manager.active_connections),
        "connections": list(manager.active_connections.keys())
    }


@router.get("/meetings/list")
async def list_meetings(
    start_date: str = None,
    end_date: str = None,
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
):
    """获取已保存的会议列表（从数据库检索，支持日期筛选）"""
    start_time = time.time()
    request_id = str(uuid.uuid4())
    
    input_params = {
        "start_date": start_date,
        "end_date": end_date,
        "limit": limit,
        "offset": offset
    }
    logger.info(f"获取会议列表请求", extra={'request_id': request_id, 'input_params': input_params})
    
    try:
        from db.session import get_all_meetings
        
        meetings, total = get_all_meetings(
            limit=limit,
            offset=offset,
            start_date=start_date,
            end_date=end_date,
            viewer=current_user,
        )

        duration_ms = (time.time() - start_time) * 1000
        output_params = {
            "success": True,
            "total": total,
            "page_count": len(meetings),
            "duration_ms": round(duration_ms, 2),
        }
        logger.info(
            "获取会议列表成功",
            extra={
                "request_id": request_id,
                "output_params": output_params,
                "duration_ms": duration_ms,
            },
        )

        return {
            "success": True,
            "total": total,
            "meetings": meetings,
        }
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        error_params = {"error": str(e), "error_type": type(e).__name__, "duration_ms": round(duration_ms, 2)}
        logger.error(f"获取会议列表失败", exc_info=True, extra={'request_id': request_id, 'output_params': error_params, 'duration_ms': duration_ms})
        return {
            "success": False,
            "error": "加载会议列表失败，请稍后重试",
        }


@router.get("/meetings/{file_id}")
async def get_meeting(file_id: str, current_user: User = Depends(get_current_user)):
    """获取指定会议的详细内容"""
    start_time = time.time()
    request_id = str(uuid.uuid4())
    
    input_params = {"file_id": file_id}
    logger.info(f"获取会议详情请求", extra={'request_id': request_id, 'input_params': input_params})
    
    try:
        from db.session import check_meeting_access, get_db_session
        from api.permissions import can_download_meeting
        from db.models import Meeting, User

        exists, allowed = check_meeting_access(file_id, current_user)
        if not exists:
            return {"success": False, "error": "会议不存在"}
        if not allowed:
            return {"success": False, "error": "无权查看该会议"}

        can_download = False
        with get_db_session() as session:
            meeting_row = session.query(Meeting).filter(Meeting.file_id == file_id).first()
            if meeting_row:
                owner = None
                if meeting_row.user_id:
                    owner = session.query(User).filter(User.id == meeting_row.user_id).first()
                can_download = can_download_meeting(current_user, meeting_row, owner, session=session)

        import json as json_lib
        from db.session import get_meeting_by_file_id
        from llm.visual_schema import visual_dict_for_display

        meeting_record = get_meeting_by_file_id(file_id)
        transcript = None
        summary = None
        summary_visual = None
        summary_visual_status = None
        transcript_file = None
        summary_file = None

        if meeting_record:
            transcript = meeting_record.transcript
            summary = meeting_record.summary
            summary_visual_status = meeting_record.summary_visual_status
            transcript_file = meeting_record.transcript_file_path
            summary_file = meeting_record.summary_file_path
            if meeting_record.summary_visual:
                summary_visual = visual_dict_for_display(meeting_record.summary_visual)

        transcripts_dir = os.path.join(output_dir, "transcripts")
        summaries_dir = os.path.join(output_dir, "summaries")

        if not transcript:
            found_path, matched_name = _find_transcript_by_file_id(transcripts_dir, file_id)
            if found_path:
                transcript_file = found_path
                with open(found_path, "r", encoding="utf-8") as f:
                    transcript = f.read()
                if matched_name:
                    summary_path = os.path.join(
                        summaries_dir, matched_name.replace(".txt", ".md")
                    )
                    if os.path.exists(summary_path):
                        summary_file = summary_path

        if not transcript:
            duration_ms = (time.time() - start_time) * 1000
            error_params = {"error": "会议不存在", "duration_ms": round(duration_ms, 2)}
            logger.warning(
                "会议不存在",
                extra={
                    "request_id": request_id,
                    "input_params": input_params,
                    "output_params": error_params,
                    "duration_ms": duration_ms,
                },
            )
            return {"success": False, "error": "会议不存在"}

        if not summary and summary_file and os.path.exists(summary_file):
            with open(summary_file, "r", encoding="utf-8") as f:
                summary = f.read()

        if summary_visual is None and summary_file:
            visual_file = summary_file.replace(".md", "_visual.json")
            if os.path.exists(visual_file):
                try:
                    with open(visual_file, "r", encoding="utf-8") as vf:
                        summary_visual = visual_dict_for_display(vf.read())
                        if summary_visual and not summary_visual_status:
                            summary_visual_status = "completed"
                except json_lib.JSONDecodeError:
                    pass
        
        duration_ms = (time.time() - start_time) * 1000
        output_params = {
            "success": True,
            "file_id": file_id,
            "transcript_length": len(transcript),
            "has_summary": summary is not None,
            "has_visual_summary": summary_visual is not None,
            "summary_visual_status": summary_visual_status,
            "summary_length": len(summary) if summary else 0,
            "duration_ms": round(duration_ms, 2)
        }
        logger.info(f"获取会议详情成功", extra={'request_id': request_id, 'input_params': input_params, 'output_params': output_params, 'duration_ms': duration_ms})
        
        return {
            "success": True,
            "file_id": file_id,
            "meeting_name": meeting_record.meeting_name if meeting_record else None,
            "created_at": meeting_record.created_at.isoformat() if meeting_record and meeting_record.created_at else None,
            "transcript_length": len(transcript) if transcript else 0,
            "transcript": transcript,
            "summary": summary,
            "summary_visual": summary_visual,
            "summary_visual_status": summary_visual_status,
            "transcript_file": transcript_file,
            "summary_file": summary_file,
            "can_download": can_download,
        }
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        error_params = {"error": str(e), "error_type": type(e).__name__, "duration_ms": round(duration_ms, 2)}
        logger.error(f"获取会议详情失败", exc_info=True, extra={'request_id': request_id, 'input_params': input_params, 'output_params': error_params, 'duration_ms': duration_ms})
        return {
            "success": False,
            "error": "加载会议详情失败，请稍后重试",
        }


