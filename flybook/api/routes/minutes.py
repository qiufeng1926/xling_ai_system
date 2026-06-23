"""飞书妙记 AI API"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from api.auth_utils import get_current_user
from api.feishu_errors import feishu_error_to_http
from api.portal_auth import PortalUser
from integrations.feishu.docs import get_root_folder_meta
from integrations.feishu.drive_upload import upload_file_to_drive
from integrations.feishu.errors import FeishuError
from integrations.feishu.minutes import (
    create_minute_from_file_token,
    get_minute,
    get_minute_artifacts,
    search_minutes,
    wait_minute_artifacts,
)
from integrations.feishu.scopes import has_minutes_scope
from services.feishu_session import ensure_user_access_token
from services.portal_tokens import PortalTokenError, fetch_feishu_token_bundle
from utils.logger import get_logger

router = APIRouter(prefix="/minutes", tags=["飞书妙记 AI"])
logger = get_logger("minutes")

_MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200MB，会话录音上限


def _require_user_id(user: PortalUser) -> int:
    if user.user_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无法识别当前用户")
    return int(user.user_id)


def _minutes_bind_status(user_id: int) -> dict:
    try:
        bundle = fetch_feishu_token_bundle(user_id=user_id)
    except PortalTokenError:
        return {"bound": False, "minutes_authorized": False}
    scope = bundle.get("oauth_scope")
    return {
        "bound": bool(bundle.get("open_id")),
        "minutes_authorized": has_minutes_scope(scope),
        "oauth_scope": scope,
    }


@router.get("/bind-status")
def minutes_bind_status(user: PortalUser = Depends(get_current_user)):
    user_id = _require_user_id(user)
    return _minutes_bind_status(user_id)


@router.get("/search")
def minutes_search(
    user: PortalUser = Depends(get_current_user),
    query: str = Query("", max_length=50),
    page_size: int = Query(15, ge=1, le=30),
    page_token: str = Query("", max_length=256),
):
    user_id = _require_user_id(user)
    status_info = _minutes_bind_status(user_id)
    if not status_info["bound"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先绑定飞书账号")
    if not status_info["minutes_authorized"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="缺少妙记权限，请重新授权飞书")
    try:
        access_token, _ = ensure_user_access_token(user_id=user_id)
        return search_minutes(
            access_token,
            query=query,
            page_size=page_size,
            page_token=page_token,
        )
    except PortalTokenError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FeishuError as exc:
        raise feishu_error_to_http(exc) from exc


@router.post("/sessions/finish")
async def minutes_finish_session(
    user: PortalUser = Depends(get_current_user),
    file: UploadFile = File(...),
    title: str = Form("", max_length=200),
    folder_token: str = Form("", max_length=128),
    wait_ai: bool = Form(True),
):
    """录音结束后上传至飞书云空间并生成妙记，可选等待 AI 产物"""
    user_id = _require_user_id(user)
    raw_name = (file.filename or "session.webm").strip()
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="录音文件为空")
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"录音超过 {_MAX_UPLOAD_BYTES // (1024 * 1024)}MB 上限",
        )
    try:
        access_token, _ = ensure_user_access_token(user_id=user_id)
        folder = folder_token.strip()
        if not folder:
            meta = get_root_folder_meta(access_token)
            folder = (meta.get("token") or meta.get("id") or "").strip()
        file_token = upload_file_to_drive(
            access_token,
            filename=raw_name,
            content=content,
            folder_token=folder,
        )
        created = create_minute_from_file_token(access_token, file_token)
        result = {
            "minute": created,
            "artifacts": {"ready": False, "status": "processing"},
        }
        if wait_ai:
            result["artifacts"] = wait_minute_artifacts(access_token, created["token"])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PortalTokenError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FeishuError as exc:
        raise feishu_error_to_http(exc) from exc

    logger.info(
        "妙记会话完成",
        extra={"output_params": {"user_id": user_id, "minute_token": result["minute"].get("token")}},
    )
    return result


@router.get("/{minute_token}")
def minutes_detail(minute_token: str, user: PortalUser = Depends(get_current_user)):
    user_id = _require_user_id(user)
    try:
        access_token, _ = ensure_user_access_token(user_id=user_id)
        return get_minute(access_token, minute_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PortalTokenError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FeishuError as exc:
        raise feishu_error_to_http(exc) from exc


@router.get("/{minute_token}/artifacts")
def minutes_artifacts(
    minute_token: str,
    user: PortalUser = Depends(get_current_user),
    wait: bool = Query(False),
):
    user_id = _require_user_id(user)
    try:
        access_token, _ = ensure_user_access_token(user_id=user_id)
        if wait:
            return wait_minute_artifacts(access_token, minute_token)
        return get_minute_artifacts(access_token, minute_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PortalTokenError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FeishuError as exc:
        raise feishu_error_to_http(exc) from exc
