"""应用日志：服务名+时间戳.log、10MB 轮转、15 天自动清理、结构化详细记录"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import BACKEND_DIR, settings

SENSITIVE_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "secret",
        "secret_key",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api_key",
        "credential",
    }
)

SENSITIVE_HEADER_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-auth-token",
    }
)

LOG_EXTRA_KEYS = (
    "service",
    "duration_ms",
    "client_ip",
    "user_agent",
    "request",
    "response",
    "extra",
)

MAX_BODY_LOG_BYTES = 64 * 1024


class DetailedJsonFormatter(logging.Formatter):
    """输出 JSON 行，包含时间、等级、message 及 extra 中的请求/响应详情"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        for key in LOG_EXTRA_KEYS:
            if hasattr(record, key):
                value = getattr(record, key)
                if value is not None:
                    payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class ServiceRotatingFileHandler(logging.Handler):
    """日志文件命名：{service_name}_{YYYYMMDD_HHMMSS}.log，超过 max_bytes 新建文件"""

    def __init__(
        self,
        log_dir: Path,
        service_name: str,
        max_bytes: int = 10 * 1024 * 1024,
        retention_days: int = 15,
    ) -> None:
        super().__init__()
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.service_name = service_name
        self.max_bytes = max_bytes
        self.retention_days = retention_days
        self._lock = threading.RLock()
        self._file = None
        self._filepath: Path | None = None
        self._size = 0
        self._open_new_file()

    def _build_filename(self) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{self.service_name}_{ts}.log"

    def _open_new_file(self) -> None:
        with self._lock:
            if self._file is not None:
                self._file.close()
                self._file = None
            self._filepath = self.log_dir / self._build_filename()
            self._file = open(self._filepath, "a", encoding="utf-8")
            self._size = self._filepath.stat().st_size if self._filepath.exists() else 0
        self._cleanup_old_logs()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record) + "\n"
            encoded_len = len(msg.encode("utf-8"))
            with self._lock:
                if self._file is None:
                    self._open_new_file()
                self._file.write(msg)
                self._file.flush()
                self._size += encoded_len
                if self._size >= self.max_bytes:
                    self._open_new_file()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        with self._lock:
            if self._file is not None:
                self._file.close()
                self._file = None
        super().close()

    def _cleanup_old_logs(self) -> None:
        cutoff = time.time() - self.retention_days * 86400
        pattern = f"{self.service_name}_*.log"
        for path in self.log_dir.glob(pattern):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
            except OSError:
                pass


def resolve_log_dir() -> Path:
    log_dir = Path(settings.LOG_DIR)
    if not log_dir.is_absolute():
        log_dir = BACKEND_DIR / log_dir
    return log_dir


def setup_logging(service_name: str | None = None) -> None:
    """初始化根 logger：文件(JSON 详细) + 控制台(简要)"""
    name = service_name or settings.LOG_SERVICE_NAME
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    json_formatter = DetailedJsonFormatter()
    file_handler = ServiceRotatingFileHandler(
        log_dir=resolve_log_dir(),
        service_name=name,
        max_bytes=settings.LOG_MAX_BYTES,
        retention_days=settings.LOG_RETENTION_DAYS,
    )
    file_handler.setFormatter(json_formatter)
    file_handler.setLevel(level)
    root.addHandler(file_handler)

    if settings.LOG_CONSOLE:
        console = logging.StreamHandler()
        console.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
        )
        console.setLevel(level)
        root.addHandler(console)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "日志系统已启动",
        extra={
            "service": name,
            "extra": {
                "log_dir": str(resolve_log_dir()),
                "max_bytes": settings.LOG_MAX_BYTES,
                "retention_days": settings.LOG_RETENTION_DAYS,
                "level": settings.LOG_LEVEL,
            },
        },
    )


def _is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return key.lower() in SENSITIVE_KEYS or normalized in {
        re.sub(r"[^a-z0-9]", "", k) for k in SENSITIVE_KEYS
    }


def sanitize_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return "..."
    if isinstance(value, dict):
        return {str(k): sanitize_value(v, depth=depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_value(item, depth=depth + 1) for item in value[:200]]
    if isinstance(value, (bytes, bytearray)):
        return f"<binary {len(value)} bytes>"
    return value


def sanitize_mapping(data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in data.items():
        if _is_sensitive_key(str(key)):
            result[key] = "***"
        else:
            result[key] = sanitize_value(value)
    return result


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in SENSITIVE_HEADER_KEYS or _is_sensitive_key(key):
            sanitized[key] = "***"
        else:
            sanitized[key] = value
    return sanitized


def parse_body_for_log(content_type: str | None, body: bytes) -> Any:
    if not body:
        return None

    truncated = len(body) > MAX_BODY_LOG_BYTES
    payload = body[:MAX_BODY_LOG_BYTES] if truncated else body
    ctype = (content_type or "").lower()

    parsed: Any
    if "application/json" in ctype:
        try:
            parsed = json.loads(payload.decode("utf-8"))
            parsed = sanitize_mapping(parsed) if isinstance(parsed, dict) else sanitize_value(parsed)
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = payload.decode("utf-8", errors="replace")
    elif "application/x-www-form-urlencoded" in ctype:
        try:
            from urllib.parse import parse_qs

            raw = payload.decode("utf-8", errors="replace")
            form = {k: v if len(v) > 1 else v[0] for k, v in parse_qs(raw).items()}
            parsed = sanitize_mapping(form)
        except Exception:
            parsed = payload.decode("utf-8", errors="replace")
    elif ctype.startswith("multipart/form-data"):
        parsed = {
            "type": "multipart/form-data",
            "size_bytes": len(body),
            "note": "multipart 正文未完整记录，仅记录类型与大小",
        }
    else:
        text = payload.decode("utf-8", errors="replace")
        parsed = text if text.isprintable() or not text else f"<non-text {len(body)} bytes>"

    if truncated:
        return {"truncated": True, "original_size_bytes": len(body), "content": parsed}
    return parsed


def build_request_log_record(
    request,
    body_bytes: bytes,
) -> dict[str, Any]:
    headers = sanitize_headers({k: v for k, v in request.headers.items()})
    query_dict: dict[str, Any] = {}
    for key, value in request.query_params.multi_items():
        if key in query_dict:
            existing = query_dict[key]
            query_dict[key] = [*existing, value] if isinstance(existing, list) else [existing, value]
        else:
            query_dict[key] = value
    query_params = sanitize_mapping(query_dict)
    path_params = sanitize_mapping(dict(request.path_params or {}))

    return {
        "method": request.method,
        "path": request.url.path,
        "url": str(request.url),
        "query_params": query_params,
        "path_params": path_params,
        "headers": headers,
        "body": parse_body_for_log(request.headers.get("content-type"), body_bytes),
        "body_size_bytes": len(body_bytes),
        "content_type": request.headers.get("content-type"),
    }
