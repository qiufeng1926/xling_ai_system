"""当前请求的门户 JWT（供筛库等可信门户工具使用）。"""

from __future__ import annotations

from contextvars import ContextVar, Token

_portal_bearer: ContextVar[str | None] = ContextVar("portal_bearer", default=None)


def set_portal_bearer(token: str | None) -> Token:
    return _portal_bearer.set((token or "").strip() or None)


def reset_portal_bearer(token: Token) -> None:
    _portal_bearer.reset(token)


def get_portal_bearer() -> str | None:
    return _portal_bearer.get()
