"""离职申请期间限制 API 访问"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.constants.account_status import OFFBOARDING
from app.database import SessionLocal
from app.models import User
from app.utils.security import decode_access_token

_OFFBOARDING_ALLOWED_PREFIXES = (
    "/api/v1/auth/me",
    "/api/v1/auth/refresh",
    "/api/v1/offboarding",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
)


class OffboardingGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/v1") or any(path.startswith(p) for p in _OFFBOARDING_ALLOWED_PREFIXES):
            return await call_next(request)

        auth = request.headers.get("authorization") or ""
        if not auth.lower().startswith("bearer "):
            return await call_next(request)

        token = auth.split(" ", 1)[1].strip()
        username = decode_access_token(token)
        if not username:
            return await call_next(request)

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == username).first()
            if user and getattr(user, "account_status", "active") == OFFBOARDING:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "离职申请处理中，仅可使用离职交接相关功能"},
                )
        finally:
            db.close()

        return await call_next(request)
