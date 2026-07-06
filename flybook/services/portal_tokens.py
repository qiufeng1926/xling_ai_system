"""从门户获取/更新用户飞书 token"""

from __future__ import annotations

from datetime import datetime

import httpx

from config.config import flybook_internal_key, portal_api_url


class PortalTokenError(Exception):
    pass


def fetch_feishu_token_bundle(*, user_id: int) -> dict:
    base = (portal_api_url or "").strip().rstrip("/")
    key = (flybook_internal_key or "").strip()
    if not base or not key:
        raise PortalTokenError("PORTAL_API_URL 或 FLYBOOK_INTERNAL_KEY 未配置")
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            f"{base}/api/v1/auth/feishu/token-bundle",
            json={"user_id": user_id},
            headers={"X-Flybook-Service-Key": key},
        )
    if resp.status_code != 200:
        detail = resp.text[:300]
        try:
            detail = resp.json().get("detail", detail)
        except Exception:
            pass
        raise PortalTokenError(f"获取飞书凭证失败 ({resp.status_code}): {detail}")
    body = resp.json()
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        raise PortalTokenError("门户未返回飞书凭证")
    return data


def save_feishu_token_bundle(
    *,
    user_id: int,
    access_token: str,
    refresh_token: str | None,
    token_expires_at: datetime | None,
    oauth_scope: str | None = None,
) -> None:
    base = (portal_api_url or "").strip().rstrip("/")
    key = (flybook_internal_key or "").strip()
    payload = {
        "user_id": user_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_expires_at": token_expires_at.isoformat() if token_expires_at else None,
        "oauth_scope": oauth_scope,
    }
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            f"{base}/api/v1/auth/feishu/token-bundle/update",
            json=payload,
            headers={"X-Flybook-Service-Key": key},
        )
    if resp.status_code != 200:
        raise PortalTokenError(f"更新飞书凭证失败 ({resp.status_code})")
