"""调用门户后端绑定飞书账号"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from config.config import flybook_internal_key, portal_api_url
from integrations.feishu.oauth import FeishuTokenPair, FeishuUserInfo


class PortalBindError(Exception):
    pass


def bind_feishu_to_portal_user(
    *,
    user_id: int,
    feishu_user: FeishuUserInfo,
    tokens: FeishuTokenPair,
) -> None:
    base = (portal_api_url or "").strip().rstrip("/")
    key = (flybook_internal_key or "").strip()
    if not base:
        raise PortalBindError("PORTAL_API_URL 未配置")
    if not key:
        raise PortalBindError("FLYBOOK_INTERNAL_KEY 未配置")

    expires_at = datetime.now(timezone.utc).timestamp() + max(tokens.expires_in, 60)
    body = {
        "user_id": user_id,
        "open_id": feishu_user.open_id,
        "union_id": feishu_user.union_id,
        "name": feishu_user.name,
        "avatar_url": feishu_user.avatar_url,
        "email": feishu_user.email,
        "mobile": feishu_user.mobile,
        "tenant_key": feishu_user.tenant_key,
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
        "oauth_scope": tokens.scope,
    }
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            f"{base}/api/v1/auth/feishu/bind",
            json=body,
            headers={"X-Flybook-Service-Key": key},
        )
    if resp.status_code != 200:
        detail = resp.text[:300]
        try:
            detail = resp.json().get("detail", detail)
        except Exception:
            pass
        raise PortalBindError(f"绑定失败 ({resp.status_code}): {detail}")
