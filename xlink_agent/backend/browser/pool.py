"""每用户一个 Playwright BrowserContext（同步 API + 线程池，兼容 Windows/uvicorn）"""

from __future__ import annotations

import asyncio
import base64
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from browser.net_guard import assert_public_url
from config.config import browser_headless, browser_idle_ttl_sec
from utils.logger import get_logger

logger = get_logger("browser.pool")

# Playwright sync API 必须在同一线程串行使用；Windows 下 asyncio 子进程会 NotImplementedError
_pw_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pw-browser")


@dataclass
class BrowserState:
    user_id: int
    context: Any = None
    page: Any = None
    last_used: float = field(default_factory=time.time)
    url: str = "about:blank"
    last_frame_b64: str | None = None


class BrowserPool:
    def __init__(self) -> None:
        self._browser = None
        self._playwright = None
        self._states: dict[int, BrowserState] = {}
        self._lock = threading.RLock()
        self._init_error: str | None = None

    def _ensure_browser_sync(self) -> None:
        if self._browser is not None:
            return
        if self._init_error:
            raise RuntimeError(self._init_error)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            self._init_error = "未安装 playwright，请执行: pip install playwright && playwright install chromium"
            raise RuntimeError(self._init_error) from exc
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=browser_headless)
            logger.info("Chromium 已启动(sync/thread) headless=%s", browser_headless)
        except Exception as exc:
            self._init_error = f"Chromium 启动失败: {exc}"
            logger.exception("Chromium 启动失败")
            raise RuntimeError(self._init_error) from exc

    def _get_state_sync(self, user_id: int) -> BrowserState:
        with self._lock:
            self._ensure_browser_sync()
            self._cleanup_idle_sync()
            state = self._states.get(user_id)
            if state is None:
                assert self._browser is not None
                context = self._browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36"
                    ),
                    locale="zh-CN",
                    ignore_https_errors=True,
                )
                page = context.new_page()
                state = BrowserState(user_id=user_id, context=context, page=page)
                self._states[user_id] = state
            state.last_used = time.time()
            return state

    def _capture_sync(self, state: BrowserState) -> str | None:
        try:
            assert state.page is not None
            raw = state.page.screenshot(type="jpeg", quality=55)
            b64 = base64.b64encode(raw).decode("ascii")
            state.last_frame_b64 = b64
            return b64
        except Exception as exc:
            logger.warning("截图失败: %s", exc)
            return state.last_frame_b64

    def _navigate_sync(self, user_id: int, url: str) -> dict:
        try:
            url = assert_public_url(url)
        except Exception as exc:
            return {"error": str(exc), "url": url}
        last_err = ""
        with self._lock:
            state = self._get_state_sync(user_id)
            assert state.page is not None
            for attempt in range(2):
                try:
                    wait = "domcontentloaded" if attempt == 0 else "load"
                    state.page.goto(url, wait_until=wait, timeout=45000)
                    state.url = state.page.url
                    state.last_used = time.time()
                    # 空页检测：body 几乎无文本
                    try:
                        body_len = len((state.page.inner_text("body", timeout=5000) or "").strip())
                    except Exception:
                        body_len = -1
                    frame = self._capture_sync(state)
                    if body_len == 0 and attempt == 0:
                        last_err = "页面正文为空，重试中"
                        continue
                    out = {"url": state.url, "title": state.page.title(), "frame": frame}
                    if body_len == 0:
                        out["warning"] = "页面正文为空"
                        out["ok"] = False
                        out["error"] = "打开后页面无有效正文"
                    return out
                except Exception as exc:
                    last_err = str(exc).split("\n")[0][:300]
                    logger.warning("navigate 失败 attempt=%s %s: %s", attempt, url, last_err)
            return {"error": f"无法打开页面: {last_err}", "url": url, "failed_url": url}

    def _click_sync(self, user_id: int, selector: str) -> dict:
        with self._lock:
            state = self._get_state_sync(user_id)
            assert state.page is not None
            try:
                state.page.click(selector, timeout=15000)
                state.url = state.page.url
                state.last_used = time.time()
                frame = self._capture_sync(state)
                return {"url": state.url, "frame": frame}
            except Exception as exc:
                return {"error": str(exc).split("\n")[0][:300], "url": state.url}

    def _type_sync(self, user_id: int, selector: str, text: str) -> dict:
        with self._lock:
            state = self._get_state_sync(user_id)
            assert state.page is not None
            state.page.fill(selector, text, timeout=15000)
            state.last_used = time.time()
            frame = self._capture_sync(state)
            return {"url": state.url, "frame": frame}

    def _extract_sync(self, user_id: int, selector: str | None = None) -> dict:
        with self._lock:
            state = self._get_state_sync(user_id)
            assert state.page is not None
            text = ""
            used = "body"
            if selector:
                try:
                    text = state.page.locator(selector).inner_text(timeout=8000)
                    used = selector
                except Exception as exc:
                    logger.warning("selector 抽取失败，回退 body: %s", str(exc).split("\n")[0][:160])
                    text = ""
            if not text:
                try:
                    text = state.page.inner_text("body", timeout=15000)
                    used = "body"
                except Exception as exc:
                    return {"error": f"browser_extract 失败: {str(exc).split(chr(10))[0][:200]}", "url": state.url}
            state.last_used = time.time()
            return {"url": state.url, "selector": used, "text": (text or "")[:20000]}

    def _screenshot_sync(self, user_id: int) -> dict:
        with self._lock:
            state = self._get_state_sync(user_id)
            frame = self._capture_sync(state)
            return {"url": state.url, "frame": frame}

    def _peek_sync(self, user_id: int) -> dict:
        """不强制启动浏览器，仅返回已有快照。"""
        with self._lock:
            state = self._states.get(user_id)
            if not state:
                return {"url": "about:blank", "frame": None, "ready": False}
            return {"url": state.url, "frame": state.last_frame_b64, "ready": True}

    def _cleanup_idle_sync(self) -> None:
        now = time.time()
        expired = [
            uid
            for uid, st in self._states.items()
            if now - st.last_used > browser_idle_ttl_sec
        ]
        for uid in expired:
            self._release_sync(uid)

    def _release_sync(self, user_id: int) -> None:
        state = self._states.pop(user_id, None)
        if not state:
            return
        try:
            if state.context:
                state.context.close()
        except Exception:
            pass

    def _shutdown_sync(self) -> None:
        with self._lock:
            for uid in list(self._states.keys()):
                self._release_sync(uid)
            try:
                if self._browser:
                    self._browser.close()
            except Exception:
                pass
            self._browser = None
            try:
                if self._playwright:
                    self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    async def _run(self, fn, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_pw_executor, lambda: fn(*args, **kwargs))

    async def peek(self, user_id: int) -> dict:
        return await self._run(self._peek_sync, user_id)

    async def navigate(self, user_id: int, url: str) -> dict:
        return await self._run(self._navigate_sync, user_id, url)

    async def click(self, user_id: int, selector: str) -> dict:
        return await self._run(self._click_sync, user_id, selector)

    async def type_text(self, user_id: int, selector: str, text: str) -> dict:
        return await self._run(self._type_sync, user_id, selector, text)

    def _page_html_sync(self, user_id: int) -> dict:
        with self._lock:
            state = self._get_state_sync(user_id)
            assert state.page is not None
            try:
                html = state.page.content()
                state.last_used = time.time()
                return {"url": state.url, "html": html or ""}
            except Exception as exc:
                return {"error": str(exc).split("\n")[0][:300], "url": state.url}

    async def page_html(self, user_id: int) -> dict:
        return await self._run(self._page_html_sync, user_id)

    async def screenshot(self, user_id: int) -> dict:
        return await self._run(self._screenshot_sync, user_id)

    async def get_state(self, user_id: int) -> BrowserState:
        # 兼容旧调用：在线程里创建 state 后返回只读快照字段
        await self._run(self._get_state_sync, user_id)
        peek = await self.peek(user_id)
        state = BrowserState(user_id=user_id)
        state.url = peek.get("url") or "about:blank"
        state.last_frame_b64 = peek.get("frame")
        return state

    async def release(self, user_id: int) -> None:
        await self._run(self._release_sync, user_id)

    async def shutdown(self) -> None:
        await self._run(self._shutdown_sync)


browser_pool = BrowserPool()
