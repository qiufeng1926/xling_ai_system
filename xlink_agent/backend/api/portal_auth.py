"""xlink 门户统一 JWT 用户解析（无本地用户库）"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from config.config import portal_api_url
from utils.logger import get_logger

logger = get_logger("portal_auth")

PORTAL_ISSUER = "xling"
PORTAL_ROLES = frozenset({"super_admin", "admin", "user"})


@dataclass
class PortalUser:
    username: str
    user_id: int | None = None
    role: str = "user"
    nickname: str = ""
    permissions: dict[str, bool] = field(default_factory=dict)

    @property
    def is_super_admin(self) -> bool:
        return self.role == "super_admin"


def _normalize_portal_username(payload: dict) -> str:
    raw = payload.get("username") or payload.get("sub") or ""
    return str(raw).strip()


def _portal_permissions(payload: dict) -> dict[str, bool]:
    perms = payload.get("perms")
    if isinstance(perms, dict):
        return {k: bool(v) for k, v in perms.items()}
    return {}


def fetch_live_portal_profile(bearer_token: str) -> dict | None:
    base = (portal_api_url or "").strip().rstrip("/")
    if not base or not bearer_token:
        return None
    try:
        with httpx.Client(timeout=3.0, trust_env=False) as client:
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
            perms = {}
        return {
            "role": data.get("role") or "user",
            "nickname": data.get("nickname"),
            "permissions": {k: bool(v) for k, v in perms.items()},
            "user_id": data.get("id"),
        }
    except Exception as exc:
        logger.debug("拉取门户用户信息失败: %s", exc)
        return None


def resolve_user_from_payload(
    payload: dict,
    *,
    bearer_token: str | None = None,
) -> PortalUser | None:
    username = _normalize_portal_username(payload)
    if not username:
        return None

    role = payload.get("role") or "user"
    nickname = (payload.get("nickname") or username).strip() or username
    uid = payload.get("uid")
    user_id = int(uid) if uid is not None and str(uid).isdigit() else None
    perms = _portal_permissions(payload)

    live = fetch_live_portal_profile(bearer_token) if bearer_token else None
    if live is not None:
        role = live.get("role") or role
        nickname = (live.get("nickname") or nickname).strip() or username
        perms = live.get("permissions") or perms
        if live.get("user_id") is not None:
            user_id = int(live["user_id"])

    return PortalUser(
        username=username,
        user_id=user_id,
        role=role,
        nickname=nickname,
        permissions=perms,
    )
