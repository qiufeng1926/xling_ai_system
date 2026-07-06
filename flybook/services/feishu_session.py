"""确保用户飞书 access_token 有效"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from integrations.feishu.oauth import refresh_user_access_token
from services.portal_tokens import PortalTokenError, fetch_feishu_token_bundle, save_feishu_token_bundle


def ensure_user_access_token(*, user_id: int) -> tuple[str, str]:
    bundle = fetch_feishu_token_bundle(user_id=user_id)
    open_id = (bundle.get("open_id") or "").strip()
    access_token = (bundle.get("access_token") or "").strip()
    refresh_token = (bundle.get("refresh_token") or "").strip() or None
    expires_raw = bundle.get("token_expires_at")

    if not open_id or not access_token:
        raise PortalTokenError("用户尚未绑定飞书或凭证缺失，请先在飞书页完成绑定")

    expires_at: datetime | None = None
    if expires_raw:
        try:
            expires_at = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
        except ValueError:
            expires_at = None

    now = datetime.now(timezone.utc)
    if expires_at and expires_at > now + timedelta(minutes=3):
        return access_token, open_id

    if not refresh_token:
        if expires_at and expires_at <= now:
            raise PortalTokenError("飞书授权已过期，请在飞书页重新绑定")
        return access_token, open_id

    tokens = refresh_user_access_token(refresh_token)
    new_expires = now + timedelta(seconds=max(tokens.expires_in, 60))
    save_feishu_token_bundle(
        user_id=user_id,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token or refresh_token,
        token_expires_at=new_expires,
        oauth_scope=tokens.scope,
    )
    return tokens.access_token, open_id
