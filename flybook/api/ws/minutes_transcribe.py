"""飞书妙记实时转写 WebSocket（飞书 stream_recognize）"""

from __future__ import annotations

import base64
import json
import secrets
import string

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from api.auth_utils import decode_access_token
from api.portal_auth import resolve_user_from_payload
from integrations.feishu.errors import FeishuError
from integrations.feishu.speech_to_text import stream_recognize
from utils.logger import get_logger

router = APIRouter()
logger = get_logger("minutes_ws")

_ALPHANUM = string.ascii_letters + string.digits + "_"


def _new_stream_id() -> str:
    return "".join(secrets.choice(_ALPHANUM) for _ in range(16))


def _auth_user(token: str):
    payload = decode_access_token(token)
    user = resolve_user_from_payload(payload, bearer_token=token)
    if not user or user.user_id is None:
        raise ValueError("无效用户")
    return user


@router.websocket("/ws/minutes/transcribe")
async def ws_minutes_transcribe(websocket: WebSocket, token: str = Query(...)):
    try:
        user = _auth_user(token)
    except Exception:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    stream_id = _new_stream_id()
    sequence_id = 0
    connection_id = f"minutes-{user.user_id}-{stream_id}"

    await websocket.send_json({"type": "ready", "stream_id": stream_id})

    try:
        while True:
            raw = await websocket.receive()
            if raw.get("type") == "websocket.disconnect":
                break

            if "bytes" in raw and raw["bytes"]:
                pcm = raw["bytes"]
                action = 1 if sequence_id == 0 else 0
                try:
                    result = stream_recognize(
                        stream_id=stream_id,
                        sequence_id=sequence_id,
                        action=action,
                        pcm_bytes=pcm,
                    )
                    text = (result.get("recognition_text") or "").strip()
                    if text:
                        await websocket.send_json(
                            {
                                "type": "transcript",
                                "text": text,
                                "sequence_id": sequence_id,
                                "final": False,
                            }
                        )
                except FeishuError as exc:
                    await websocket.send_json({"type": "error", "message": exc.msg, "code": exc.code})
                sequence_id += 1
                continue

            text_data = raw.get("text")
            if not text_data:
                continue

            try:
                msg = json.loads(text_data)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "无效 JSON 消息"})
                continue

            msg_type = msg.get("type")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if msg_type == "stop":
                pcm_b64 = msg.get("data") or ""
                pcm = base64.b64decode(pcm_b64) if pcm_b64 else b""
                try:
                    if pcm:
                        result = stream_recognize(
                            stream_id=stream_id,
                            sequence_id=sequence_id,
                            action=0,
                            pcm_bytes=pcm,
                        )
                        text = (result.get("recognition_text") or "").strip()
                        if text:
                            await websocket.send_json(
                                {
                                    "type": "transcript",
                                    "text": text,
                                    "sequence_id": sequence_id,
                                    "final": False,
                                }
                            )
                        sequence_id += 1
                    final = stream_recognize(
                        stream_id=stream_id,
                        sequence_id=sequence_id,
                        action=2,
                        pcm_bytes=b"",
                    )
                    final_text = (final.get("recognition_text") or "").strip()
                    await websocket.send_json(
                        {
                            "type": "transcript",
                            "text": final_text,
                            "sequence_id": sequence_id,
                            "final": True,
                        }
                    )
                except FeishuError as exc:
                    await websocket.send_json({"type": "error", "message": exc.msg, "code": exc.code})
                await websocket.send_json({"type": "stopped"})
                break

            if msg_type == "audio":
                pcm_b64 = msg.get("data") or ""
                if not pcm_b64:
                    continue
                pcm = base64.b64decode(pcm_b64)
                action = int(msg.get("action", 1 if sequence_id == 0 else 0))
                seq = int(msg.get("sequence_id", sequence_id))
                try:
                    result = stream_recognize(
                        stream_id=stream_id,
                        sequence_id=seq,
                        action=action,
                        pcm_bytes=pcm,
                    )
                    text = (result.get("recognition_text") or "").strip()
                    if text:
                        await websocket.send_json(
                            {
                                "type": "transcript",
                                "text": text,
                                "sequence_id": seq,
                                "final": False,
                            }
                        )
                    sequence_id = seq + 1
                except FeishuError as exc:
                    await websocket.send_json({"type": "error", "message": exc.msg, "code": exc.code})

    except WebSocketDisconnect:
        logger.info("妙记转写 WebSocket 断开", extra={"request_id": connection_id})
    except Exception as exc:
        logger.warning("妙记转写 WebSocket 异常: %s", exc, extra={"request_id": connection_id})
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
