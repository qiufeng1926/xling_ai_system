"""统一计算用户在各模块的有效权限（写入 JWT 与 /auth/me）"""

from __future__ import annotations

from app.constants.roles import ADMIN, SUPER_ADMIN, USER
from app.models import User
from app.utils.access_control import normalize_role


def effective_permissions(user: User) -> dict[str, bool]:
    role = normalize_role(user.role)

    if role == SUPER_ADMIN:
        return {
            "view_library": True,
            "view_all_meetings": True,
            "view_root_meetings": True,
            "view_all_root_meetings": bool(getattr(user, "view_all_root_meetings", False)),
            "download_meetings": True,
            "approve_meeting_download": True,
        }

    if role == ADMIN:
        return {
            "view_library": bool(getattr(user, "view_library", False)),
            "view_all_meetings": bool(getattr(user, "view_all_meetings", False)),
            "view_root_meetings": bool(getattr(user, "view_root_meetings", False)),
            "view_all_root_meetings": False,
            "download_meetings": bool(getattr(user, "download_meetings", False)),
            "approve_meeting_download": bool(getattr(user, "approve_meeting_download", False)),
        }

    return {
        "view_library": bool(getattr(user, "view_library", False)),
        "view_all_meetings": bool(getattr(user, "view_all_meetings", False)),
        "view_root_meetings": False,
        "view_all_root_meetings": False,
        "download_meetings": bool(getattr(user, "download_meetings", False)),
        "approve_meeting_download": False,
    }


def user_has_permission(user: User, perm: str) -> bool:
    return effective_permissions(user).get(perm, False)


def can_apply_request_type(user: User, request_type: str) -> tuple[bool, str]:
    from app.constants.permissions import (
        REQ_DOWNLOAD_MEETINGS,
        REQ_PROMOTE_ADMIN,
        REQ_VIEW_ALL_MEETINGS,
        REQ_VIEW_LIBRARY,
        REQ_VIEW_ROOT_MEETINGS,
    )

    perms = effective_permissions(user)
    role = normalize_role(user.role)

    if request_type == REQ_VIEW_LIBRARY:
        if perms["view_library"]:
            return False, "您已拥有达人库查阅权限"
        return True, ""

    if request_type == REQ_VIEW_ALL_MEETINGS:
        if perms["view_all_meetings"]:
            return False, "您已拥有查看全部会议的权限"
        return True, ""

    if request_type == REQ_DOWNLOAD_MEETINGS:
        if role == SUPER_ADMIN or perms["download_meetings"]:
            return False, "您已拥有会议导出/下载权限"
        return True, ""

    if request_type == REQ_VIEW_ROOT_MEETINGS:
        if role != ADMIN:
            return False, "仅管理员可申请查看超级管理员会议"
        if perms["view_root_meetings"]:
            return False, "您已拥有查看超级管理员会议的权限"
        return True, ""

    if request_type == REQ_PROMOTE_ADMIN:
        if role in (SUPER_ADMIN, ADMIN):
            return False, "您已是管理员"
        return True, ""

    return False, "未知申请类型"
