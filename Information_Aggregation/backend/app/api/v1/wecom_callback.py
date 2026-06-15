"""企业微信应用回调（接收消息服务器 URL 校验 + 事件推送占位）"""

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse

from app.config import settings
from app.integrations.wecom.callback_crypto import WeComCallbackError, decrypt_message, verify_url

router = APIRouter(prefix="/wecom", tags=["企业微信回调"])


def _require_callback_config() -> tuple[str, str, str]:
    token = (settings.WECOM_CALLBACK_TOKEN or "").strip()
    aes_key = (settings.WECOM_ENCODING_AES_KEY or "").strip()
    corp_id = (settings.WECOM_CORP_ID or "").strip()
    if not token or not aes_key or not corp_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "请在 backend/.env 配置 WECOM_CALLBACK_TOKEN、WECOM_ENCODING_AES_KEY、WECOM_CORP_ID，"
                "并与管理后台「接收消息」里填写的 Token / EncodingAESKey 完全一致"
            ),
        )
    return token, aes_key, corp_id


@router.get("/callback", response_class=PlainTextResponse)
def wecom_callback_verify(
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
):
    """企微保存「接收消息服务器 URL」时的 GET 校验"""
    token, aes_key, corp_id = _require_callback_config()
    try:
        plain = verify_url(
            token=token,
            encoding_aes_key=aes_key,
            corp_id=corp_id,
            msg_signature=msg_signature,
            timestamp=timestamp,
            nonce=nonce,
            echostr=echostr,
        )
    except WeComCallbackError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PlainTextResponse(content=plain, media_type="text/plain")


@router.post("/callback")
async def wecom_callback_event(
    request: Request,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
):
    """接收审批状态变更等事件（当前仅解密校验并返回 success）"""
    token, aes_key, corp_id = _require_callback_config()
    body = await request.body()
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(body.decode("utf-8"))
        encrypt = (root.findtext("Encrypt") or "").strip()
        if not encrypt:
            raise WeComCallbackError("回调 body 缺少 Encrypt")
        decrypt_message(
            token=token,
            encoding_aes_key=aes_key,
            corp_id=corp_id,
            msg_signature=msg_signature,
            timestamp=timestamp,
            nonce=nonce,
            encrypt=encrypt,
        )
    except WeComCallbackError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ET.ParseError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="回调 XML 无效") from exc
    return Response(content="success", media_type="text/plain")
