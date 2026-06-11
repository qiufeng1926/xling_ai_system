"""采集平台登录态管理（星图 / 蒲公英）"""

from __future__ import annotations

import json
import logging
import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.utils.cookie_import import build_storage_state, storage_state_to_bytes
from app.services.collection_service import CollectionService

logger = logging.getLogger(__name__)

PLATFORM_CONFIG: dict[str, dict[str, str]] = {
    "douyin": {
        "label": "星图（抖音）",
        "storage_setting": "XINGTU_STORAGE_STATE",
        "login_url": "https://www.xingtu.cn/ad/creator/market",
    },
    "xiaohongshu": {
        "label": "蒲公英（小红书）",
        "storage_setting": "PUGONGYING_STORAGE_STATE",
        "login_url": "https://pgy.xiaohongshu.com/solar/pre-trade/note/kol",
    },
}

_lock = threading.Lock()
_active_logins: dict[str, "_LoginSession"] = {}

_worker_queue: queue.Queue["_WorkerCommand | None"] = queue.Queue()
_worker_thread: threading.Thread | None = None
_worker_lock = threading.Lock()


@dataclass
class _LoginSession:
    playwright: Any
    browser: Any
    context: Any
    page: Any
    started_at: datetime
    error: str | None = None


@dataclass
class _WorkerCommand:
    action: str
    platform: str = ""
    payload: Any = None
    event: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: BaseException | None = None


def _ensure_worker() -> None:
    global _worker_thread
    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            return
        _worker_thread = threading.Thread(
            target=_playwright_worker_loop,
            daemon=True,
            name="playwright-session-worker",
        )
        _worker_thread.start()


def _run_on_worker(action: str, platform: str = "", payload: Any = None, timeout: float = 90) -> Any:
    """所有 Playwright 操作必须在同一工作线程执行"""
    _ensure_worker()
    cmd = _WorkerCommand(action=action, platform=platform, payload=payload)
    _worker_queue.put(cmd)
    if not cmd.event.wait(timeout=timeout):
        raise TimeoutError(f"Playwright 操作超时: {action}")
    if cmd.error is not None:
        raise cmd.error
    return cmd.result


def _playwright_worker_loop() -> None:
    while True:
        cmd = _worker_queue.get()
        if cmd is None:
            break
        try:
            if cmd.action == "start":
                cmd.result = _worker_start_login(cmd.platform)
            elif cmd.action == "save":
                cmd.result = _worker_save_login(cmd.platform)
            elif cmd.action == "cancel":
                cmd.result = _worker_close_session(cmd.platform)
            else:
                raise ValueError(f"未知 Playwright 指令: {cmd.action}")
        except BaseException as exc:
            cmd.error = exc
            logger.exception("Playwright worker failed: action=%s platform=%s", cmd.action, cmd.platform)
        finally:
            cmd.event.set()


def _worker_start_login(platform: str) -> dict[str, Any]:
    cfg = _require_platform(platform)
    _worker_close_session(platform)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        with _lock:
            _active_logins[platform] = _LoginSession(
                None, None, None, None, datetime.now(), error="Playwright 未安装"
            )
        raise RuntimeError("Playwright 未安装") from exc

    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        page = context.new_page()
        page.goto(cfg["login_url"], wait_until="domcontentloaded", timeout=60000)

        with _lock:
            _active_logins[platform] = _LoginSession(pw, browser, context, page, datetime.now())
        logger.info("Login browser opened for %s", platform)
        return {"ok": True}
    except Exception as exc:
        logger.exception("Failed to open login browser for %s", platform)
        with _lock:
            _active_logins[platform] = _LoginSession(
                None, None, None, None, datetime.now(), error=str(exc)
            )
        raise


def _worker_save_login(platform: str) -> dict[str, Any]:
    _require_platform(platform)

    with _lock:
        session = _active_logins.get(platform)
        if not session or session.error:
            raise ValueError("没有进行中的登录流程，请先点击「打开浏览器登录」")
        context = session.context
        if not context:
            raise ValueError("登录浏览器未就绪，请稍后重试")

    path = SessionService.get_storage_path(platform)
    path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(path))
    _worker_close_session(platform)
    logger.info("Saved storage state for %s: %s", platform, path)
    return {"path": str(path)}


def _worker_close_session(platform: str) -> None:
    with _lock:
        session = _active_logins.pop(platform, None)
    if not session:
        return

    for target in (session.page, session.context, session.browser):
        if target is None:
            continue
        try:
            target.close()
        except Exception:
            pass
    if session.playwright is not None:
        try:
            session.playwright.stop()
        except Exception:
            pass


class SessionService:
    @staticmethod
    def list_sessions() -> list[dict[str, Any]]:
        return [SessionService.get_session_status(platform) for platform in PLATFORM_CONFIG]

    @staticmethod
    def get_session_status(platform: str) -> dict[str, Any]:
        cfg = _require_platform(platform)
        env = CollectionService.check_environment(platform)
        storage_path = SessionService.get_storage_path(platform)

        with _lock:
            session = _active_logins.get(platform)
            login_active = session is not None and not session.error
            login_error = session.error if session else None

        return {
            **env,
            "platform": platform,
            "label": cfg["label"],
            "login_url": cfg["login_url"],
            "storage_path": str(storage_path),
            "login_in_progress": login_active,
            "login_error": login_error,
        }

    @staticmethod
    def get_storage_path(platform: str) -> Path:
        cfg = _require_platform(platform)
        path_str = getattr(settings, cfg["storage_setting"], "")
        if not path_str:
            raise ValueError(f"未配置 {cfg['storage_setting']}")
        return Path(path_str)

    @staticmethod
    def import_cookies(platform: str, content: str) -> dict[str, Any]:
        _require_platform(platform)
        state = build_storage_state(platform, content)
        return SessionService.upload_storage_state(platform, storage_state_to_bytes(state))

    @staticmethod
    def upload_storage_state(platform: str, content: bytes) -> dict[str, Any]:
        _validate_storage_state(content)
        path = SessionService.get_storage_path(platform)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        logger.info("Uploaded storage state for %s: %s", platform, path)
        return SessionService.get_session_status(platform)

    @staticmethod
    def delete_storage_state(platform: str) -> dict[str, Any]:
        _require_platform(platform)
        SessionService.cancel_login(platform)
        path = SessionService.get_storage_path(platform)
        if path.exists():
            path.unlink()
            logger.info("Deleted storage state for %s: %s", platform, path)
        return SessionService.get_session_status(platform)

    @staticmethod
    def start_login(platform: str) -> dict[str, Any]:
        _require_platform(platform)

        with _lock:
            existing = _active_logins.get(platform)
            if existing and not existing.error:
                raise ValueError("已有进行中的登录流程，请先保存或取消")

        try:
            _run_on_worker("cancel", platform, timeout=30)
        except Exception:
            pass

        try:
            _run_on_worker("start", platform, timeout=90)
        except Exception as exc:
            _run_on_worker("cancel", platform, timeout=30)
            raise RuntimeError(str(exc)) from exc

        status = SessionService.get_session_status(platform)
        if status.get("login_error"):
            _run_on_worker("cancel", platform, timeout=30)
            raise RuntimeError(status["login_error"])
        if not status.get("login_in_progress"):
            raise RuntimeError(
                "浏览器未能启动，请确认本机已安装 Chromium（playwright install chromium）"
            )
        return status

    @staticmethod
    def save_login(platform: str) -> dict[str, Any]:
        _require_platform(platform)
        _run_on_worker("save", platform, timeout=60)
        return SessionService.get_session_status(platform)

    @staticmethod
    def cancel_login(platform: str) -> dict[str, Any]:
        _require_platform(platform)
        _run_on_worker("cancel", platform, timeout=30)
        return SessionService.get_session_status(platform)


def _require_platform(platform: str) -> dict[str, str]:
    cfg = PLATFORM_CONFIG.get(platform)
    if not cfg:
        raise ValueError(f"不支持的平台: {platform}")
    return cfg


def _validate_storage_state(content: bytes) -> None:
    if len(content) > 2 * 1024 * 1024:
        raise ValueError("登录态文件过大（最大 2MB）")

    try:
        data = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("无效的 JSON 文件") from exc

    if not isinstance(data, dict):
        raise ValueError("登录态格式不正确")

    if "cookies" not in data or not isinstance(data["cookies"], list):
        raise ValueError("登录态文件需包含 cookies 数组（Playwright storage_state 格式）")
