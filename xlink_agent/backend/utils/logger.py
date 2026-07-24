"""xlink-agent 日志：控制台 + 按日/按大小滚动的文件。

文件名：{service_name}_{YYYYMMDD_HHMMSS}.log
滚动条件（满足其一即新建）：
- 跨自然日
- 当前文件达到 LOG_MAX_BYTES（默认 30MB）
"""

from __future__ import annotations

import logging
import sys
import threading
from datetime import datetime
from pathlib import Path

_DEFAULT = "xlink-agent"
_MAX_BYTES_DEFAULT = 30 * 1024 * 1024


class DailyOrSizeRotatingFileHandler(logging.FileHandler):
    """按自然日或文件大小滚动；每次滚动使用新的 service_时间戳 文件名。"""

    def __init__(
        self,
        log_dir: str | Path,
        service_name: str,
        *,
        max_bytes: int = _MAX_BYTES_DEFAULT,
        encoding: str = "utf-8",
    ) -> None:
        self.log_dir = Path(log_dir)
        self.service_name = service_name
        self.max_bytes = max(1, int(max_bytes))
        self._day = ""
        self._lock_rotate = threading.RLock()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        path = self._alloc_path()
        super().__init__(path, mode="a", encoding=encoding, delay=False)

    def _alloc_path(self) -> Path:
        now = datetime.now()
        self._day = now.strftime("%Y%m%d")
        # 含毫秒，避免同一秒内按大小滚动时文件名冲突
        ts = now.strftime("%Y%m%d_%H%M%S_%f")[:-3]  # YYYYMMDD_HHMMSS_mmm
        path = self.log_dir / f"{self.service_name}_{ts}.log"
        # 极端碰撞再追加序号
        if path.exists():
            n = 1
            while True:
                cand = self.log_dir / f"{self.service_name}_{ts}_{n}.log"
                if not cand.exists():
                    return cand
                n += 1
        return path

    def _current_size(self) -> int:
        try:
            if self.stream is not None:
                self.stream.flush()
                return int(self.stream.tell())
        except Exception:
            pass
        try:
            path = Path(self.baseFilename)
            if path.exists():
                return int(path.stat().st_size)
        except OSError:
            pass
        return 0

    def _should_rotate(self) -> bool:
        today = datetime.now().strftime("%Y%m%d")
        if today != self._day:
            return True
        return self._current_size() >= self.max_bytes

    def _do_rotate(self) -> None:
        try:
            if self.stream:
                self.stream.flush()
                self.stream.close()
        except Exception:
            pass
        self.stream = None  # type: ignore[assignment]
        new_path = self._alloc_path()
        self.baseFilename = str(new_path)
        self.stream = self._open()

    def emit(self, record: logging.LogRecord) -> None:
        with self._lock_rotate:
            try:
                if self._should_rotate():
                    self._do_rotate()
            except Exception:
                self.handleError(record)
            super().emit(record)


def setup_logging(
    service_name: str | None = None,
    console: bool = True,
    *,
    force: bool = True,
) -> logging.Logger:
    from config.config import log_dir, log_level, log_service_name

    try:
        from config.config import log_max_bytes as _cfg_max
    except Exception:
        _cfg_max = _MAX_BYTES_DEFAULT

    name = (service_name or log_service_name or _DEFAULT).strip() or _DEFAULT
    logger = logging.getLogger(name)

    if logger.handlers and not force:
        return logger

    for h in list(logger.handlers):
        logger.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass

    level = getattr(logging, str(log_level).upper(), logging.INFO)
    logger.setLevel(level)
    # 只走本 logger 的 handler，避免与 uvicorn root 重复或被吞掉
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if console:
        # stderr：uvicorn/reload 下比 stdout 更不易被吞；与 access log 也能区分开
        sh = logging.StreamHandler(sys.stderr)
        sh.setLevel(level)
        sh.setFormatter(fmt)
        logger.addHandler(sh)

    max_bytes = int(_cfg_max) if _cfg_max else _MAX_BYTES_DEFAULT
    fh = DailyOrSizeRotatingFileHandler(
        log_dir,
        name,
        max_bytes=max_bytes,
        encoding="utf-8",
    )
    fh.setLevel(level)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    logger.debug(
        "logging ready console=%s dir=%s max_bytes=%s",
        console,
        log_dir,
        max_bytes,
    )
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """返回挂在服务根 logger 下的子 logger（日志写入同一套 handler）。"""
    from config.config import log_service_name

    root_name = (log_service_name or _DEFAULT).strip() or _DEFAULT
    base = logging.getLogger(root_name)
    # 若尚未 setup（例如单测直接 import），补一次，保证有控制台+文件
    if not base.handlers:
        setup_logging(service_name=root_name, console=True, force=True)
    if name:
        return base.getChild(name)
    return base
