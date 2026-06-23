"""飞书开放平台事件回调（URL 校验 + 事件推送占位）"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from config.config import feishu_encrypt_key, feishu_verification_token
from integrations.feishu.callback_crypto import FeishuCallbackError, decrypt_event, verify_signature
from utils.logger import get_logger

router = APIRouter(tags=["飞书回调"])
logger = get_logger("callback")


def _require_callback_config() -> tuple[str, str]:
    token = (feishu_verification_token or "").strip()
    encrypt_key = (feishu_encrypt_key or "").strip()
    if not token or not encrypt_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "请在 flybook/.env 配置 FEISHU_VERIFICATION_TOKEN 与 FEISHU_ENCRYPT_KEY，"
                "并与飞书开放平台「事件订阅」中填写的值完全一致"
            ),
        )
    return token, encrypt_key


@router.post("/callback")
async def feishu_callback(request: Request):
    """飞书事件订阅回调（challenge 校验 + 加密事件解密）"""
    verification_token, encrypt_key = _require_callback_config()
    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8")

    try:
        payload = json.loads(body_text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="回调 body 无效 JSON") from exc

    # URL 校验（首次配置事件订阅）
    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge")
        if payload.get("token") != verification_token:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification Token 不匹配")
        if not challenge:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少 challenge")
        return JSONResponse({"challenge": challenge})

    timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
    nonce = request.headers.get("X-Lark-Request-Nonce", "")
    signature = request.headers.get("X-Lark-Signature", "")

    try:
        verify_signature(
            timestamp=timestamp,
            nonce=nonce,
            encrypt_key=encrypt_key,
            body=body_text,
            signature=signature,
        )
    except FeishuCallbackError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    encrypt = payload.get("encrypt")
    if encrypt:
        try:
            event = decrypt_event(encrypt_key, encrypt)
        except FeishuCallbackError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        logger.info(
            "收到飞书事件",
            extra={"output_params": {"event_type": event.get("header", {}).get("event_type")}},
        )

    return JSONResponse({})
