"""Flybook 日志模块（JSON Lines，按体积轮转）"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

MAX_FILE_BYTES = 15 * 1024 * 1024
DEFAULT_RETENTION_DAYS = 15
_DEFAULT_LOGGER_NAME = "flybook"


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        dt = datetime.fromtimestamp(record.created)
        try:
            time_str = dt.isoformat(timespec="milliseconds")
        except TypeError:
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")

        payload: dict = {
            "time": time_str,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "filename": record.filename,
            "lineno": record.lineno,
            "funcName": record.funcName,
        }
        if hasattr(record, "request_id"):
            payload["request_id"] = record.request_id
        if hasattr(record, "input_params"):
            payload["input_params"] = record.input_params
        if hasattr(record, "output_params"):
            payload["output_params"] = record.output_params
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info).rstrip()
        return json.dumps(payload, ensure_ascii=False, default=str)


class TimestampSizeRotatingHandler(logging.Handler):
    def __init__(
        self,
        log_dir: Path,
        service_name: str,
        max_bytes: int = MAX_FILE_BYTES,
        retention_days: int = DEFAULT_RETENTION_DAYS,
    ):
        super().__init__()
        self.terminator = "\n"
        self.log_dir = Path(log_dir)
        self.service_name = service_name
        self.max_bytes = max_bytes
        self.retention_days = retention_days
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.base_path: Path | None = None
        self.stream = None
        self._open_new_file()
        self._purge_old_files()

    def _new_filepath(self) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.log_dir / f"{self.service_name}_{ts}.log"

    def _open_new_file(self) -> None:
        if self.stream:
            self.stream.close()
            self.stream = None
        self.base_path = self._new_filepath()
        self.stream = open(self.base_path, "a", encoding="utf-8")

    def _purge_old_files(self) -> None:
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        current = self.base_path.name if self.base_path else None
        for path in self.log_dir.glob(f"{self.service_name}_*.log"):
            if current and path.name == current:
                continue
            try:
                if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
                    path.unlink(missing_ok=True)
            except OSError:
                continue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.acquire()
            try:
                if self.stream is None or self.base_path is None:
                    self._open_new_file()
                assert self.stream is not None and self.base_path is not None
                self.stream.write(msg + self.terminator)
                self.stream.flush()
                if self.base_path.stat().st_size >= self.max_bytes:
                    self.stream.close()
                    self.base_path = self._new_filepath()
                    self.stream = open(self.base_path, "a", encoding="utf-8")
                    self._purge_old_files()
            finally:
                self.release()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        self.acquire()
        try:
            if self.stream:
                self.stream.close()
                self.stream = None
        finally:
            self.release()
            super().close()


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def setup_logging(
    service_name: str | None = None,
    log_dir: str | Path | None = None,
    level: int = logging.INFO,
    logger_name: str = _DEFAULT_LOGGER_NAME,
    console: bool = True,
) -> logging.Logger:
    env_lvl = os.getenv("LOG_LEVEL", "").strip().upper()
    if env_lvl:
        level = getattr(logging, env_lvl, level)

    name = service_name or os.getenv("LOG_SERVICE_NAME") or "flybook"
    root_log = Path(log_dir) if log_dir else Path(os.getenv("LOG_DIR", _project_root() / "logs"))

    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    logger.propagate = False

    if not any(isinstance(h, TimestampSizeRotatingHandler) for h in logger.handlers):
        fh = TimestampSizeRotatingHandler(root_log, service_name=name)
        fh.setFormatter(JsonLineFormatter())
        fh.setLevel(level)
        logger.addHandler(fh)

    if console and not any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, TimestampSizeRotatingHandler)
        for h in logger.handlers
    ):
        ch = logging.StreamHandler()
        ch.setLevel(level)
        ch.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
        logger.addHandler(ch)

    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    base = logging.getLogger(_DEFAULT_LOGGER_NAME)
    if not base.handlers:
        setup_logging(logger_name=_DEFAULT_LOGGER_NAME)
    if not name or name == _DEFAULT_LOGGER_NAME:
        return base
    return logging.getLogger(f"{_DEFAULT_LOGGER_NAME}.{name}")
