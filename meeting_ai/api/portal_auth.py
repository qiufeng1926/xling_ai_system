"""xling 门户统一 JWT 用户解析（与 Information_Aggregation 共用密钥与账号）"""

from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from config.config import portal_api_url
from db.models import User
from utils.password import hash_password

PORTAL_ISSUER = "xling"
PORTAL_ROLES = frozenset({"super_admin", "admin", "user"})

ROLE_TO_MEETING = {
    "super_admin": "root",
    "admin": "admin",
    "user": "user",
}

PERM_TO_MEETING_FIELD = {
    "view_all_meetings": "can_view_all",
    "view_root_meetings": "can_view_root_meetings",
    "view_all_root_meetings": "can_view_all_roots",
    "download_meetings": "can_download",
    "approve_meeting_download": "can_approve_download",
    "approve_meeting_view": "can_approve_view",
}


def _normalize_portal_username(payload: dict) -> str:
    """从门户 JWT 解析用户名（sub / username 均可）"""
    raw = payload.get("username") or payload.get("sub") or ""
    return str(raw).strip()


def is_portal_token(payload: dict) -> bool:
    if payload.get("iss") == PORTAL_ISSUER:
        return True
    role = payload.get("role")
    return role in PORTAL_ROLES and not str(payload.get("sub", "")).isdigit()


def _unusable_password_hash() -> str:
    import secrets

    return hash_password(secrets.token_urlsafe(32))


def _portal_permissions(payload: dict) -> dict[str, bool]:
    perms = payload.get("perms")
    if isinstance(perms, dict):
        return {k: bool(v) for k, v in perms.items()}

    portal_role = payload.get("role") or "user"
    if portal_role == "super_admin":
        return {
            "view_all_meetings": True,
            "view_root_meetings": True,
            "view_all_root_meetings": False,
            "download_meetings": True,
            "approve_meeting_download": True,
            "approve_meeting_view": True,
        }
    if portal_role == "admin":
        return {
            "view_all_meetings": False,
            "view_root_meetings": False,
            "view_all_root_meetings": False,
            "download_meetings": False,
            "approve_meeting_download": False,
            "approve_meeting_view": False,
        }
    return {
        "view_all_meetings": False,
        "view_root_meetings": False,
        "view_all_root_meetings": False,
        "download_meetings": False,
        "approve_meeting_download": False,
        "approve_meeting_view": False,
    }


def fetch_live_portal_profile(bearer_token: str) -> dict | None:
    """从门户 /auth/me 拉取最新角色与权限（超级管理员下发后立即生效）"""
    base = (portal_api_url or "").strip().rstrip("/")
    if not base or not bearer_token:
        return None
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(
                f"{base}/api/v1/auth/me",
                headers={"Authorization": f"Bearer {bearer_token}"},
            )
        if resp.status_code != 200:
            return None
        body = resp.json()
        data = body.get("data")
        if not isinstance(data, dict):
            return None
        perms = data.get("permissions")
        if not isinstance(perms, dict):
            return None
        return {
            "role": data.get("role") or "user",
            "nickname": data.get("nickname"),
            "permissions": {k: bool(v) for k, v in perms.items()},
        }
    except Exception:
        return None


def fetch_live_portal_permissions(bearer_token: str) -> dict[str, bool] | None:
    profile = fetch_live_portal_profile(bearer_token)
    if profile is None:
        return None
    return profile.get("permissions")


def _apply_portal_permissions(user: User, perms: dict[str, bool]) -> None:
    for perm_key, field in PERM_TO_MEETING_FIELD.items():
        if perm_key in perms:
            setattr(user, field, bool(perms[perm_key]))


def _sync_portal_user_fields(user: User, *, nickname: str, meeting_role: str, perms: dict[str, bool]) -> None:
    if nickname and user.nickname != nickname:
        user.nickname = nickname
    if user.role != meeting_role:
        user.role = meeting_role
    _apply_portal_permissions(user, perms)


def get_or_create_user_from_portal_token(
    db: Session,
    payload: dict,
    *,
    bearer_token: str | None = None,
) -> User | None:
    username = _normalize_portal_username(payload)
    if not username:
        return None

    portal_role = payload.get("role") or "user"
    meeting_role = ROLE_TO_MEETING.get(portal_role, "user")
    nickname = (payload.get("nickname") or username).strip() or username
    perms = _portal_permissions(payload)
    live_profile = fetch_live_portal_profile(bearer_token) if bearer_token else None
    if live_profile is not None:
        perms = live_profile["permissions"]
        portal_role = live_profile.get("role") or portal_role
        meeting_role = ROLE_TO_MEETING.get(portal_role, meeting_role)
        nickname = (live_profile.get("nickname") or nickname).strip() or username

    user = db.query(User).filter(User.username == username).first()
    if user:
        _sync_portal_user_fields(user, nickname=nickname, meeting_role=meeting_role, perms=perms)
        db.commit()
        db.refresh(user)
        return user

    user = User(
        username=username,
        nickname=nickname,
        password_hash=_unusable_password_hash(),
        role=meeting_role,
        can_view_all=bool(perms.get("view_all_meetings")),
        can_view_root_meetings=bool(perms.get("view_root_meetings")),
        can_view_all_roots=bool(perms.get("view_all_root_meetings")),
        can_download=bool(perms.get("download_meetings")),
        can_approve_download=bool(perms.get("approve_meeting_download")),
        can_approve_view=bool(perms.get("approve_meeting_view")),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def resolve_user_from_payload(
    db: Session,
    payload: dict,
    *,
    bearer_token: str | None = None,
) -> User | None:
    if is_portal_token(payload):
        return get_or_create_user_from_portal_token(db, payload, bearer_token=bearer_token)

    sub = payload.get("sub")
    if sub is not None and str(sub).isdigit():
        return db.query(User).filter(User.id == int(sub)).first()

    username = payload.get("username") or sub
    if username:
        return db.query(User).filter(User.username == str(username).strip()).first()
    return None
