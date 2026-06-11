"""
会议 AI 系统日志模块：写入项目根目录下 logs/ 文件夹；
每条日志为单行 JSON（JSON Lines）；单文件超过 15MB 轮转；超过保留天数自动清理。
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

# 配置常量
MAX_FILE_BYTES = 15 * 1024 * 1024  # 15MB
DEFAULT_RETENTION_DAYS = 15
_DEFAULT_LOGGER_NAME = "meeting_ai"


class JsonLineFormatter(logging.Formatter):
    """将 LogRecord 格式化为单行 JSON（便于检索与解析）。"""

    def format(self, record: logging.LogRecord) -> str:
        dt = datetime.fromtimestamp(record.created)
        try:
            time_str = dt.isoformat(timespec="milliseconds")
        except TypeError:
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        
        payload: dict = {
            "time": time_str,
            "level": record.levelname,
            "levelno": record.levelno,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "filename": record.filename,
            "lineno": record.lineno,
            "funcName": record.funcName,
            "thread": record.threadName,
            "process": record.process,
        }
        
        # 添加自定义字段（如果存在）
        if hasattr(record, 'request_id'):
            payload["request_id"] = record.request_id
        if hasattr(record, 'user_id'):
            payload["user_id"] = record.user_id
        if hasattr(record, 'input_params'):
            payload["input_params"] = self._sanitize_data(record.input_params)
        if hasattr(record, 'output_params'):
            payload["output_params"] = self._sanitize_data(record.output_params)
        if hasattr(record, 'duration_ms'):
            payload["duration_ms"] = record.duration_ms
        if hasattr(record, 'status_code'):
            payload["status_code"] = record.status_code
        
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info).rstrip()
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info).rstrip()
        
        return json.dumps(payload, ensure_ascii=False, default=str)
    
    def _sanitize_data(self, data) -> any:
        """清理敏感数据，防止日志泄露密码等敏感信息"""
        if isinstance(data, dict):
            sanitized = {}
            for key, value in data.items():
                # 跳过敏感字段
                if key.lower() in ['password', 'token', 'api_key', 'secret', 'authorization']:
                    sanitized[key] = '***REDACTED***'
                else:
                    sanitized[key] = self._sanitize_data(value)
            return sanitized
        elif isinstance(data, (list, tuple)):
            return [self._sanitize_data(item) for item in data]
        elif isinstance(data, (str, int, float, bool, type(None))):
            return data
        else:
            # 其他类型转换为字符串
            return str(data)


class TimestampSizeRotatingHandler(logging.Handler):
    """按体积轮转：超过阈值后关闭当前文件并以新时间戳创建 .log。"""

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

    def _find_reusable_file(self) -> Path | None:
        """uvicorn --reload 重启时复用刚创建的日志，避免一次启动多个文件"""
        candidates = sorted(
            self.log_dir.glob(f"{self.service_name}_*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        now = datetime.now()
        for path in candidates:
            if path.stat().st_size >= self.max_bytes:
                continue
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            if (now - mtime).total_seconds() <= 120:
                return path
        return None

    def _open_new_file(self) -> None:
        if self.stream:
            self.stream.close()
            self.stream = None
        reusable = self._find_reusable_file()
        self.base_path = reusable if reusable else self._new_filepath()
        self.stream = open(self.base_path, "a", encoding="utf-8")

    def _purge_old_files(self) -> None:
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        current = self.base_path.name if self.base_path else None
        for pattern in (f"{self.service_name}_*.log", f"{self.service_name}.log"):
            for path in self.log_dir.glob(pattern):
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


_exception_hooks_installed = False
_warnings_capture_done = False


def _install_exception_hooks(logger: logging.Logger) -> None:
    """
    将未捕获的主线程 / 子线程异常写入同一 logger（含完整 traceback）。
    Gradio 等库常在 worker 线程抛错，仅依赖 sys.excepthook 不够。
    """
    global _exception_hooks_installed
    if _exception_hooks_installed:
        return
    _exception_hooks_installed = True

    prev_sys = sys.excepthook

    def _sys_excepthook(exc_type, exc, tb) -> None:
        if exc_type is not None and issubclass(exc_type, KeyboardInterrupt):
            prev_sys(exc_type, exc, tb)
            return
        logger.critical("未捕获的全局异常", exc_info=(exc_type, exc, tb))
        prev_sys(exc_type, exc, tb)

    sys.excepthook = _sys_excepthook

    if hasattr(threading, "excepthook"):
        prev_th = threading.excepthook

        def _thread_excepthook(args: object) -> None:
            logger.critical(
                "未捕获的线程异常 thread=%r",
                getattr(args, "thread", None),
                exc_info=(
                    getattr(args, "exc_type", None),
                    getattr(args, "exc_value", None),
                    getattr(args, "exc_traceback", None),
                ),
            )
            try:
                prev_th(args)
            except Exception:
                pass

        threading.excepthook = _thread_excepthook


def setup_logging(
    service_name: str | None = None,
    log_dir: str | Path | None = None,
    level: int = logging.INFO,
    logger_name: str = _DEFAULT_LOGGER_NAME,
    max_bytes: int = MAX_FILE_BYTES,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    console: bool = True,
) -> logging.Logger:
    """
    初始化命名日志器（默认 meeting_ai），挂载文件 Handler；可选控制台输出。
    重复调用不会重复添加同类 Handler。
    """
    global _warnings_capture_done

    env_lvl = os.getenv("LOG_LEVEL", "").strip().upper()
    if env_lvl:
        level = getattr(logging, env_lvl, level)

    name = service_name or os.getenv("LOG_SERVICE_NAME") or "meeting_ai"
    root_log = Path(log_dir) if log_dir else Path(os.getenv("LOG_DIR", _project_root() / "logs"))

    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    logger.propagate = False

    # 详细格式，包含源码位置，便于对齐 traceback
    _detail_fmt = (
        "%(asctime)s | %(levelname)s | %(name)s | %(filename)s:%(lineno)d | %(message)s"
    )

    has_file_handler = any(
        isinstance(h, TimestampSizeRotatingHandler) for h in logger.handlers
    )
    if not has_file_handler:
        fh = TimestampSizeRotatingHandler(
            root_log,
            service_name=name,
            max_bytes=max_bytes,
            retention_days=retention_days,
        )
        fh.setFormatter(JsonLineFormatter())
        fh.setLevel(level)
        logger.addHandler(fh)

    ch: logging.StreamHandler | None = None
    if console and not any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, TimestampSizeRotatingHandler)
        for h in logger.handlers
    ):
        ch = logging.StreamHandler()
        ch.setLevel(level)
        ch.setFormatter(logging.Formatter(_detail_fmt))
        logger.addHandler(ch)

    # 未捕获异常、warnings 也写入同一批 handler
    _install_exception_hooks(logger)
    if not _warnings_capture_done:
        logging.captureWarnings(True)
        _warnings_capture_done = True
    wlog = logging.getLogger("py.warnings")
    wlog.setLevel(logging.WARNING)
    wlog.propagate = False
    for h in list(logger.handlers):
        if h not in wlog.handlers:
            wlog.addHandler(h)

    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """获取日志器；首次使用时先初始化 meeting_ai（含文件 Handler）。

    子模块使用 ``meeting_ai.<name>`` 层级命名，使日志向上传播到 meeting_ai 的 Handler。
    """
    base = logging.getLogger(_DEFAULT_LOGGER_NAME)
    if not base.handlers:
        setup_logging(logger_name=_DEFAULT_LOGGER_NAME)
    if not name or name == _DEFAULT_LOGGER_NAME:
        return base
    return logging.getLogger(f"{_DEFAULT_LOGGER_NAME}.{name}")


def log_request(
    logger: logging.Logger,
    message: str,
    request_id: str = None,
    input_params: dict = None,
    level: int = logging.INFO,
    **kwargs
):
    """
    记录请求日志
    
    Args:
        logger: 日志器实例
        message: 日志消息
        request_id: 请求 ID
        input_params: 输入参数字典
        level: 日志级别
        **kwargs: 其他额外字段
    """
    extra = {'input_params': input_params, **kwargs}
    if request_id:
        extra['request_id'] = request_id
    logger.log(level, message, extra=extra)


def log_response(
    logger: logging.Logger,
    message: str,
    request_id: str = None,
    output_params: dict = None,
    duration_ms: float = None,
    status_code: int = None,
    level: int = logging.INFO,
    **kwargs
):
    """
    记录响应日志
    
    Args:
        logger: 日志器实例
        message: 日志消息
        request_id: 请求 ID
        output_params: 输出参数字典
        duration_ms: 处理耗时（毫秒）
        status_code: 状态码
        level: 日志级别
        **kwargs: 其他额外字段
    """
    extra = {'output_params': output_params, **kwargs}
    if request_id:
        extra['request_id'] = request_id
    if duration_ms is not None:
        extra['duration_ms'] = duration_ms
    if status_code is not None:
        extra['status_code'] = status_code
    logger.log(level, message, extra=extra)


def log_api_call(
    logger: logging.Logger,
    api_name: str,
    request_id: str = None,
    input_params: dict = None,
    output_params: dict = None,
    duration_ms: float = None,
    status_code: int = None,
    error: Exception = None,
):
    """
    记录完整的 API 调用日志（包含请求和响应）
    
    Args:
        logger: 日志器实例
        api_name: API 名称
        request_id: 请求 ID
        input_params: 输入参数
        output_params: 输出参数
        duration_ms: 处理耗时（毫秒）
        status_code: 状态码
        error: 异常对象（如果有）
    """
    extra = {
        'input_params': input_params,
        'output_params': output_params,
    }
    if request_id:
        extra['request_id'] = request_id
    if duration_ms is not None:
        extra['duration_ms'] = duration_ms
    if status_code is not None:
        extra['status_code'] = status_code
    
    if error:
        logger.error(f"API 调用失败: {api_name}", exc_info=error, extra=extra)
    else:
        logger.info(f"API 调用成功: {api_name}", extra=extra)
