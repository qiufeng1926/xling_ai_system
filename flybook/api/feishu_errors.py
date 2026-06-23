"""飞书 API 错误 → HTTP 响应"""

from __future__ import annotations

from fastapi import HTTPException, status

from integrations.feishu.errors import FeishuError


def feishu_error_to_http(exc: FeishuError) -> HTTPException:
    if exc.code == 99991679 or "99991679" in exc.msg:
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "feishu_scope_missing",
                "message": (
                    "当前飞书授权缺少云文档权限（如 drive:drive、docx:document）。"
                    "请在云文档页点击「重新授权」完成绑定；"
                    "并确认飞书开放平台已为应用开通对应用户身份权限。"
                ),
                "feishu_code": exc.code,
                "feishu_message": exc.msg,
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
