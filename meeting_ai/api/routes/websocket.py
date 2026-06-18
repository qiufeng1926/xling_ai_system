import json
import re
import uuid
import os
import time
import asyncio
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


def _find_tingwu_summary_file(file_id: str) -> str | None:
    summaries_dir = os.path.join(output_dir, "summaries")
    if not os.path.isdir(summaries_dir):
        return None
    for name in os.listdir(summaries_dir):
        if name.endswith("_tingwu.json") and file_id in name:
            return os.path.join(summaries_dir, name)
    return None
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, HTTPException
from api.auth_utils import get_user_from_token, get_current_user
from db.models import User
from db.session import SessionFactory
from utils.logger import get_logger
from asr.tingwu_realtime import TingwuRealtimeEngine, TingwuTaskError
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
                f"WebSocket 发送失败: {type(e).__name__}",
                extra={"request_id": connection_id, "msg_type": data.get("type")},
            )
            self.disconnect(connection_id)
            return False
        except Exception as e:
            logger.warning(
                f"WebSocket 发送异常: {e}",
                extra={"request_id": connection_id, "msg_type": data.get("type")},
            )
            self.disconnect(connection_id)
            return False


manager = ConnectionManager()


def _extract_tingwu_from_transcriber(transcriber) -> tuple[str | None, dict | None, str]:
    if transcriber is None:
        return None, None, "skipped"
    task_id = getattr(transcriber, "task_id", None)
    data = getattr(transcriber, "summarization_data", None)
    status = getattr(transcriber, "summarization_status", "skipped") or "skipped"
    return task_id, data, status


async def _save_tingwu_summarization_files(
    safe_name: str,
    file_id: str,
    timestamp: str,
    tingwu_data: dict | None,
) -> tuple[str | None, str | None]:
    if not tingwu_data:
        return None, None
    tingwu_filename = f"{safe_name}_{file_id}_{timestamp}_tingwu.json"
    tingwu_path = os.path.join(output_dir, "summaries", tingwu_filename)
    tingwu_json = json.dumps(tingwu_data, ensure_ascii=False, indent=2)
    await run_io(Path(tingwu_path).write_text, tingwu_json, encoding="utf-8")
    return tingwu_path, tingwu_json


def _tingwu_meeting_fields(
    task_id: str | None,
    tingwu_data: dict | None,
    tingwu_status: str,
    tingwu_path: str | None,
    tingwu_json: str | None,
) -> dict:
    return {
        "tingwu_task_id": task_id,
        "tingwu_summarization": tingwu_json,
        "tingwu_summarization_status": tingwu_status,
        "tingwu_summarization_file_path": tingwu_path,
    }


def _tingwu_session_end_fields(file_id: str, tingwu_data: dict | None, tingwu_status: str) -> dict:
    return {
        "has_tingwu_summary": bool(tingwu_data),
        "tingwu_summarization_status": tingwu_status,
        "tingwu_summary_page": f"/tingwu-summary?file_id={file_id}",
    }


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

    meeting_name = (session_info.get("meeting_name") or "").strip()
    if not meeting_name:
        return None

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

    safe_name = "".join(
        c for c in meeting_name if c.isalnum() or c in (" ", "-", "_")
    ).strip().replace(" ", "_")
    transcript_filename = f"{safe_name}_{file_id}_{timestamp}_realtime.txt"
    transcript_path = os.path.join(output_dir, "transcripts", transcript_filename)
    await run_io(Path(transcript_path).write_text, total_text, encoding="utf-8")

    tingwu_task_id, tingwu_data, tingwu_status = _extract_tingwu_from_transcriber(transcriber)
    tingwu_path, tingwu_json = await _save_tingwu_summarization_files(
        safe_name, file_id, timestamp, tingwu_data
    )
    tingwu_db_fields = _tingwu_meeting_fields(
        tingwu_task_id, tingwu_data, tingwu_status, tingwu_path, tingwu_json
    )

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
        **tingwu_db_fields,
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
    }
    tingwu_start_lock = asyncio.Lock()

    async def _tingwu_periodic_keepalive() -> None:
        """听悟侧定期发送静音，避免长时间静音或浏览器节流导致 IDLE_TIMEOUT。"""
        try:
            while session_info.get("tingwu_started") and not session_info.get("saved"):
                await asyncio.sleep(12)
                if session_info.get("tingwu_failed"):
                    break
                transcriber_ref = session_info.get("transcriber")
                if transcriber_ref is None or getattr(transcriber_ref, "_closed", False):
                    break
                await tingwu_engine.send_keepalive_async(transcriber_ref)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(
                f"听悟保活失败: {e}",
                extra={"request_id": connection_id},
            )

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
                    _tingwu_periodic_keepalive()
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
                raw_message = await asyncio.wait_for(websocket.receive(), timeout=25.0)
            except asyncio.TimeoutError:
                await manager.send_json(
                    connection_id,
                    {"type": "heartbeat", "stage": "recording"},
                )
                continue

            if raw_message.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect()

            if "bytes" in raw_message:
                audio_bytes = raw_message["bytes"]
                if not audio_bytes:
                    continue
                if session_info.get("tingwu_failed"):
                    continue
                await ensure_tingwu_started()
                session_info["audio_chunks"] += 1
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
                    if not meeting_name:
                        await manager.send_json(connection_id, {
                            "type": "error",
                            "message": "会议名称为必填项，请填写后重新开始录音",
                        })
                        continue
                    session_info["meeting_name"] = meeting_name
                    logger.info(f"设置会议名称", extra={'request_id': connection_id, 'input_params': {'meeting_name': meeting_name}})
                    continue

                if message.get("type") == "ping":
                    await manager.send_json(connection_id, {"type": "pong"})
                    continue

                if message.get("type") == "record_start":
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
                    await tingwu_engine.feed_stream_async(
                        session_info["transcriber"], audio_bytes, sample_rate
                    )
                    session_info["total_text"] = session_info["transcriber"].total_text()

                elif message.get("type") == "end":
                    if session_info["tingwu_started"]:
                        await manager.send_json(connection_id, {
                            "type": "generating_transcript",
                            "message": "正在整理说话人分离转写并获取听悟 AI 摘要，请稍候...",
                        })
                        await tingwu_engine.finalize_stream_async(session_info["transcriber"])
                        session_info["tingwu_finalized"] = True
                        session_info["total_text"] = session_info["transcriber"].total_text()

                    # 会话结束，生成 AI 总结
                    duration_ms = (time.time() - start_time) * 1000
                    logger.info(f"会话结束，开始生成 AI 总结", extra={'request_id': connection_id, 'output_params': {'duration_ms': round(duration_ms, 2), 'total_text_length': len(session_info["total_text"]), 'audio_chunks': session_info["audio_chunks"]}})
                    
                    # 保存转写文本
                    file_id = str(uuid.uuid4())
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    session_info["file_id"] = file_id
                    
                    # 构建文件名（包含会议名称）
                    meeting_name = (session_info.get("meeting_name") or "").strip()
                    if not meeting_name:
                        await manager.send_json(connection_id, {
                            "type": "error",
                            "message": "会议名称为必填项，请填写后重新开始录音",
                        })
                        continue
                    safe_name = "".join(c for c in meeting_name if c.isalnum() or c in (' ', '-', '_')).strip()
                    safe_name = safe_name.replace(' ', '_')
                    transcript_filename = f"{safe_name}_{file_id}_{timestamp}_realtime.txt"
                    summary_filename = f"{safe_name}_{file_id}_{timestamp}_realtime.md"
                    
                    # 异步保存转写文本
                    transcript_path = os.path.join(
                        output_dir, "transcripts",
                        transcript_filename
                    )
                    await run_io(Path(transcript_path).write_text, session_info["total_text"], encoding='utf-8')
                    logger.info(f"实时转写文本已保存", extra={'request_id': connection_id, 'output_params': {'transcript_file': transcript_path, 'text_length': len(session_info["total_text"])}})

                    transcriber = session_info.get("transcriber")
                    tingwu_task_id, tingwu_data, tingwu_status = _extract_tingwu_from_transcriber(transcriber)
                    tingwu_path, tingwu_json = await _save_tingwu_summarization_files(
                        safe_name, file_id, timestamp, tingwu_data
                    )
                    tingwu_db_fields = _tingwu_meeting_fields(
                        tingwu_task_id, tingwu_data, tingwu_status, tingwu_path, tingwu_json
                    )
                    tingwu_client_fields = _tingwu_session_end_fields(file_id, tingwu_data, tingwu_status)
                    
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
                    await manager.send_json(connection_id, {
                        "type": "generating_summary",
                        "message": "正在生成文字与图文速览...",
                        "file_id": file_id,
                    })

                    # 并行生成 Markdown + 图文速览（期间发送心跳保活）
                    try:
                        dual = await _run_with_keepalive(
                            connection_id,
                            generate_dual_summaries(
                                get_llm_client(),
                                session_info["total_text"],
                                meeting_name or None,
                                session_info.get("start_time"),
                            ),
                            stage="summary",
                        )
                        if dual.markdown_error or not dual.markdown:
                            raise RuntimeError(dual.markdown_error or 'Markdown 速览生成失败')

                        summary = dual.markdown
                        summary_visual_dict = visual_dict_from_result(dual)

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
                                'meeting_name': meeting_name if meeting_name else None,
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
                                **tingwu_db_fields,
                            }
                            await save_meeting_to_db_async(meeting_data)
                            session_info["saved"] = True
                            logger.info(f"实时会议数据已保存到数据库", extra={'request_id': connection_id})
                        except Exception as db_error:
                            logger.error(f"保存实时会议数据到数据库失败: {str(db_error)}", exc_info=True, extra={'request_id': connection_id})

                        end_result = {
                            "type": "session_end",
                            "summary": summary,
                            "summary_visual": summary_visual_dict,
                            "summary_visual_status": dual.visual_status,
                            "summary_visual_error": dual.visual_error,
                            "summary_file": summary_path,
                            **tingwu_client_fields,
                            **end_result_base,
                        }
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
                            meeting_data = {
                                'file_id': file_id,
                                'user_id': session_info["user_id"],
                                'meeting_name': meeting_name if meeting_name else None,
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
                                **tingwu_db_fields,
                            }
                            await save_meeting_to_db_async(meeting_data)
                            session_info["saved"] = True
                            logger.info(f"失败的实时会议数据已保存到数据库", extra={'request_id': connection_id})
                        except Exception as db_error:
                            logger.error(f"保存失败的实时会议数据到数据库失败: {str(db_error)}", exc_info=True, extra={'request_id': connection_id})
                        
                        end_result = {
                            "type": "session_end",
                            "summary": None,
                            "error": "会议纪要生成失败，请稍后重试",
                            **tingwu_client_fields,
                            **end_result_base,
                        }
                        await manager.send_json(connection_id, end_result)

                    break
                    
            except json.JSONDecodeError:
                logger.warning(
                    "无法解析 WebSocket 文本消息",
                    extra={"request_id": connection_id},
                )
    
    except WebSocketDisconnect:
        duration_ms = (time.time() - start_time) * 1000
        logger.info(f"WebSocket 断开连接", extra={'request_id': connection_id, 'output_params': {'duration_ms': round(duration_ms, 2), 'total_text_length': len(session_info["total_text"]), 'audio_chunks': session_info["audio_chunks"]}})
    except RuntimeError as e:
        if "close message" in str(e).lower():
            logger.info(f"WebSocket 已关闭", extra={'request_id': connection_id})
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
        logger.error(f"WebSocket 错误", exc_info=True, extra={'request_id': connection_id, 'output_params': {'error': str(e), 'error_type': type(e).__name__, 'duration_ms': round(duration_ms, 2)}})
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

        transcriber = session_info.get("transcriber")
        if (
            transcriber is not None
            and session_info.get("tingwu_started")
            and not session_info.get("tingwu_finalized")
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
        logger.info(f"会话清理完成", extra={'request_id': connection_id})


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
            "has_tingwu_summary": bool(
                meeting_record and meeting_record.tingwu_summarization
            ) if meeting_record else bool(
                _find_tingwu_summary_file(file_id)
            ),
            "tingwu_summarization_status": (
                meeting_record.tingwu_summarization_status if meeting_record else None
            ),
            "tingwu_summary_page": f"/tingwu-summary?file_id={file_id}",
        }
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        error_params = {"error": str(e), "error_type": type(e).__name__, "duration_ms": round(duration_ms, 2)}
        logger.error(f"获取会议详情失败", exc_info=True, extra={'request_id': request_id, 'input_params': input_params, 'output_params': error_params, 'duration_ms': duration_ms})
        return {
            "success": False,
            "error": "加载会议详情失败，请稍后重试",
        }


