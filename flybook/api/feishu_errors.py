"""飞书 API 错误 → HTTP 响应"""

from __future__ import annotations

import re

from fastapi import HTTPException, status

from integrations.feishu.errors import FeishuError

_PRIVILEGE_RE = re.compile(r"privileges(?: under the user identity)?:\s*\[([^\]]+)\]", re.IGNORECASE)


def _extract_required_privileges(msg: str) -> list[str]:
    match = _PRIVILEGE_RE.search(msg or "")
    if not match:
        return []
    return [part.strip() for part in match.group(1).split(",") if part.strip()]


def _scope_missing_message(msg: str) -> str:
    required = _extract_required_privileges(msg)
    if required:
        scope_hint = "、".join(required[:4])
    else:
        scope_hint = "相关用户身份权限"

    if any("minutes" in item for item in required):
        return (
            f"当前飞书授权缺少妙记权限（{scope_hint}）。"
            "请在飞书开发者后台开通对应用户身份权限，并在妙记 AI 页点击「重新授权」。"
        )
    if any(item.startswith("drive:") or item.startswith("docx:") or item.startswith("docs:") for item in required):
        return (
            f"当前飞书授权缺少云文档权限（{scope_hint}）。"
            "请在云文档页点击「重新授权」；并确认飞书开放平台已为应用开通对应用户身份权限。"
        )
    return (
        f"当前飞书授权缺少权限（{scope_hint}）。"
        "请在飞书开发者后台开通对应用户身份权限后重新授权。"
    )


def feishu_error_to_http(exc: FeishuError) -> HTTPException:
    if exc.code == 99991679 or "99991679" in exc.msg:
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "feishu_scope_missing",
                "message": _scope_missing_message(exc.msg),
                "feishu_code": exc.code,
                "feishu_message": exc.msg,
                "required_privileges": _extract_required_privileges(exc.msg),
            },
        )
    if exc.code in (99991663, 99991668, 99991677):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "feishu_token_invalid",
                "message": "飞书授权无效或已过期，请重新绑定飞书账号",
                "feishu_code": exc.code,
            },
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={"code": "feishu_api_error", "message": exc.msg, "feishu_code": exc.code},
    )


def portal_token_to_http(exc: Exception) -> HTTPException:
    """PortalTokenError → 结构化 HTTP 响应（便于前端提示重新绑定）"""
    from services.portal_tokens import PortalTokenError

    if not isinstance(exc, PortalTokenError):
        raise exc
    msg = str(exc)
    if "PORTAL_API_URL" in msg or "FLYBOOK_INTERNAL_KEY 未配置" in msg:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "flybook_config_error", "message": msg},
        )
    if "无效的服务密钥" in msg:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "portal_internal_key_mismatch",
                "message": "flybook 与门户 FLYBOOK_INTERNAL_KEY 不一致，请联系管理员",
            },
        )
    if "用户尚未绑定" in msg or "凭证缺失" in msg:
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "feishu_not_bound", "message": msg},
        )
    if "已过期" in msg:
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "feishu_token_invalid", "message": "飞书授权已过期，请重新绑定"},
        )
    if "获取飞书凭证失败" in msg:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "portal_unreachable", "message": msg},
        )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": "feishu_token_error", "message": msg},
    )
