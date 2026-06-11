import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.utils.logging_config import build_request_log_record, sanitize_headers

logger = logging.getLogger("api.access")

SKIP_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico"})


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        body_bytes = await request.body()

        async def receive():
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        request = Request(request.scope, receive)
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        request_data = build_request_log_record(request, body_bytes)
        response_data = {
            "status_code": response.status_code,
            "headers": sanitize_headers(
                {k: v for k, v in response.headers.items() if k.lower() in ("content-type", "content-length")}
            ),
        }
        client = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        log_level = logging.INFO
        if response.status_code >= 500:
            log_level = logging.ERROR
        elif response.status_code >= 400:
            log_level = logging.WARNING

        logger.log(
            log_level,
            "%s %s -> %s (%.0fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={
                "duration_ms": round(duration_ms, 2),
                "client_ip": client,
                "user_agent": user_agent,
                "request": request_data,
                "response": response_data,
            },
        )
        return response
