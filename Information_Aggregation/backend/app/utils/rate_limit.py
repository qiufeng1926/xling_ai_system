"""内存级登录限流（单实例有效；多实例部署需改用 Redis）"""

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from app.config import settings

_attempts: dict[str, list[float]] = defaultdict(list)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def check_login_rate_limit(request: Request) -> None:
    key = _client_key(request)
    now = time.time()
    window = settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS
    max_attempts = settings.LOGIN_RATE_LIMIT_MAX_ATTEMPTS

    attempts = _attempts[key]
    attempts[:] = [t for t in attempts if now - t < window]

    if len(attempts) >= max_attempts:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录尝试过于频繁，请稍后再试",
        )


def record_login_failure(request: Request) -> None:
    _attempts[_client_key(request)].append(time.time())


def clear_login_attempts(request: Request) -> None:
    _attempts.pop(_client_key(request), None)
