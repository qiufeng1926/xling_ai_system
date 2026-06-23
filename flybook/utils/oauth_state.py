"""OAuth state 签名（防 CSRF）"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def make_oauth_state(secret: str, *, return_to: str = "", user_id: int | None = None) -> str:
    payload = {
        "n": secrets.token_urlsafe(8),
        "exp": int(time.time()) + 600,
        "rt": (return_to or "").strip()[:512],
    }
    if user_id is not None:
        payload["uid"] = int(user_id)
    data = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()
    return f"{data}.{sig}"


def verify_oauth_state(secret: str, state: str) -> dict:
    if not state or "." not in state:
        raise ValueError("无效的 state")
    data, sig = state.rsplit(".", 1)
    expected = hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise ValueError("state 签名校验失败")
    payload = json.loads(_b64url_decode(data))
    if int(payload.get("exp") or 0) < int(time.time()):
        raise ValueError("state 已过期")
    return payload
