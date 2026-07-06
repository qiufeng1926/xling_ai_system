"""飞书 OAuth 绑定（须先登录 xlink 门户）"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from api.auth_utils import get_current_user
from api.portal_auth import PortalUser
from config.config import feishu_app_id, feishu_oauth_redirect_uri, feishu_oauth_scope, jwt_secret, portal_frontend_url
from integrations.feishu.errors import FeishuError
from integrations.feishu.oauth import (
    build_authorize_url,
    exchange_code_for_tokens,
    fetch_user_info,
)
from services.portal_bind import PortalBindError, bind_feishu_to_portal_user
from utils.logger import get_logger
from utils.oauth_state import make_oauth_state, verify_oauth_state

router = APIRouter(prefix="/auth", tags=["飞书绑定"])
logger = get_logger("auth")

FLYBOOK_HOME = "/flybook/messenger"


class BindStartResponse(BaseModel):
    authorize_url: str
    redirect_uri: str
    app_id: str


def _frontend_return_url(*, path: str = FLYBOOK_HOME, bind: str | None = None, error: str | None = None) -> str:
    base = (portal_frontend_url or "http://localhost:5173").rstrip("/")
    safe_path = path if path.startswith("/") else FLYBOOK_HOME
    params: dict[str, str] = {}
    if bind:
        params["bind"] = bind
    if error:
        params["bind_error"] = error
    qs = urlencode(params)
    return f"{base}{safe_path}{f'?{qs}' if qs else ''}"


@router.get("/status")
def feishu_bind_status(user: PortalUser = Depends(get_current_user)):
    """由 flybook 代理查询时可用；推荐前端直接调门户 /api/v1/auth/feishu/status"""
    return {"bound": False, "hint": "请调用门户 /api/v1/auth/feishu/status"}


@router.get("/oauth-config")
def feishu_oauth_config():
    """诊断：当前 OAuth 配置（便于与飞书后台重定向 URL 对照）"""
    return {
        "app_id": feishu_app_id or "",
        "redirect_uri": feishu_oauth_redirect_uri,
        "scope": feishu_oauth_scope,
        "feishu_console_path": "开发者后台 → 你的应用 → 开发配置 → 安全设置 → 重定向 URL",
        "checklist": [
            "重定向 URL 须与 redirect_uri 完全一致（含 https、域名、路径，不要多余斜杠）",
            "App ID 须与 FEISHU_APP_ID 一致",
            "权限管理须已开通并生效：drive:drive、docx:document、docx:document:create、offline_access（用户身份）",
            "云文档用户须在 xlink 重新绑定飞书以获取新 scope（仅 refresh 无法补权限）",
            "自建应用需已启用；修改重定向 URL 后点击保存",
        ],
    }


@router.post("/bind/start", response_model=BindStartResponse)
def feishu_bind_start(
    user: PortalUser = Depends(get_current_user),
    return_to: str = Query(FLYBOOK_HOME, max_length=512),
):
    """已登录用户发起飞书授权绑定"""
    if not feishu_app_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="飞书 OAuth 未配置，请在 flybook/.env 设置 FEISHU_APP_ID 与 FEISHU_APP_SECRET",
        )
    if user.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法识别当前用户，请重新登录后再绑定飞书",
        )
    state = make_oauth_state(jwt_secret, return_to=return_to, user_id=user.user_id)
    try:
        url = build_authorize_url(state=state)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    logger.info(
        "发起飞书绑定",
        extra={
            "output_params": {
                "user_id": user.user_id,
                "redirect_uri": feishu_oauth_redirect_uri,
                "app_id": feishu_app_id,
            }
        },
    )
    return BindStartResponse(
        authorize_url=url,
        redirect_uri=feishu_oauth_redirect_uri,
        app_id=feishu_app_id or "",
    )


@router.get("/callback")
def feishu_bind_callback(
    code: str = Query("", max_length=512),
    state: str = Query("", max_length=1024),
    error: str = Query("", max_length=64),
):
    """飞书 OAuth 回调：绑定到 state 中的门户用户"""
    user_id: int | None = None
    return_path = FLYBOOK_HOME
    try:
        payload = verify_oauth_state(jwt_secret, state)
        raw_uid = payload.get("uid")
        if raw_uid is not None:
            user_id = int(raw_uid)
        rt = (payload.get("rt") or "").strip()
        if rt.startswith("/"):
            return_path = rt[:512]
    except ValueError:
        return RedirectResponse(
            _frontend_return_url(error="invalid_state"),
            status_code=status.HTTP_302_FOUND,
        )

    if user_id is None:
        return RedirectResponse(
            _frontend_return_url(path=return_path, error="missing_user"),
            status_code=status.HTTP_302_FOUND,
        )

    if error == "access_denied":
        return RedirectResponse(
            _frontend_return_url(path=return_path, error="access_denied"),
            status_code=status.HTTP_302_FOUND,
        )
    if not code:
        return RedirectResponse(
            _frontend_return_url(path=return_path, error="missing_code"),
            status_code=status.HTTP_302_FOUND,
        )

    try:
        tokens = exchange_code_for_tokens(code)
        feishu_user = fetch_user_info(tokens.access_token)
        bind_feishu_to_portal_user(user_id=user_id, feishu_user=feishu_user, tokens=tokens)
    except FeishuError as exc:
        logger.warning("飞书 OAuth 失败: %s", exc)
        return RedirectResponse(
            _frontend_return_url(path=return_path, error="feishu_api_error"),
            status_code=status.HTTP_302_FOUND,
        )
    except PortalBindError as exc:
        logger.warning("飞书绑定失败: %s", exc)
        msg = str(exc)
        if "该飞书账号已绑定其他系统用户" in msg:
            err = "already_bound"
        elif "无效的服务密钥" in msg:
            err = "invalid_service_key"
        else:
            err = "bind_failed"
        return RedirectResponse(
            _frontend_return_url(path=return_path, error=err),
            status_code=status.HTTP_302_FOUND,
        )

    return RedirectResponse(
        _frontend_return_url(path=return_path, bind="success"),
        status_code=status.HTTP_302_FOUND,
    )
