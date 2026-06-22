"""蒲公英 Playwright 自动化采集器（小红书博主）"""

import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.collectors.base import RawInfluencer, SearchFilters
from app.collectors.filter_utils import passes_search_filters
from app.config import settings
from app.utils.mcn_utils import extract_mcn_name
from app.utils.collector_uid import pick_display_nickname, resolve_pugongying_platform_uid
from app.utils.collected_parsed import resolve_collected_profile_url
from app.utils.keyword_match import calc_keyword_match_score, passes_keyword_match
from app.utils.pugongying_fields import (
    AVATAR_KEYS,
    FOLLOWER_KEYS,
    KOL_ID_KEYS,
    NICKNAME_KEYS,
    TAG_KEYS,
    build_pugongying_kol_url,
    choose_best_profile_url,
    parse_dom_text_fields,
    parse_pugongying_item,
)
from app.utils.xingtu_fields import merge_author_items

logger = logging.getLogger(__name__)

PUGONGYING_MARKET_URL = "https://pgy.xiaohongshu.com/solar/pre-trade/note/kol"
PUGONGYING_SEARCH_URL = "https://pgy.xiaohongshu.com/solar/pre-trade/note/kol?keyword={keyword}"

INTERCEPT_URL_KEYWORDS = (
    "search",
    "search_kol",
    "kol/search",
    "blogger/search",
)

EXCLUDE_URL_KEYWORDS = (
    "recommend",
    "suggest",
    "/login",
)

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _save_failure_screenshot(page, keyword: str) -> str | None:
    if page is None:
        return None
    try:
        log_dir = BACKEND_DIR / "logs" / "screenshots"
        log_dir.mkdir(parents=True, exist_ok=True)
        safe_kw = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", keyword)[:20] or "keyword"
        from datetime import datetime

        filename = f"pgy_fail_{datetime.now():%Y%m%d_%H%M%S}_{safe_kw}.png"
        path = log_dir / filename
        page.screenshot(path=str(path), full_page=True)
        return str(path)
    except Exception:
        logger.exception("Failed to save screenshot")
        return None


class PugongyingBrowserCollector:
    """通过 Playwright 操作蒲公英找博主，拦截 API 获取小红书达人数据"""

    def search(self, keyword: str, filters: SearchFilters) -> list[RawInfluencer]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("请先安装 Playwright: pip install playwright && playwright install chromium") from exc

        logger.info("Pugongying Playwright collect start: keyword=%s", keyword)
        authors: dict[str, dict[str, Any]] = {}
        from_search_api = False

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=settings.PLAYWRIGHT_HEADLESS,
                slow_mo=settings.PLAYWRIGHT_SLOW_MO,
            )
            context = self._create_context(browser)
            page = None
            api_authors: dict[str, dict[str, Any]] = {}

            try:
                page = context.new_page()

                def on_response(response) -> None:
                    nonlocal from_search_api
                    if response.status != 200:
                        return
                    content_type = response.headers.get("content-type", "")
                    if "json" not in content_type:
                        return
                    url = response.url.lower()
                    if "xiaohongshu.com" not in url and "xhs.cn" not in url:
                        return
                    if any(k in url for k in EXCLUDE_URL_KEYWORDS):
                        return
                    if not any(k in url for k in INTERCEPT_URL_KEYWORDS):
                        return
                    try:
                        data = response.json()
                        for item in _extract_kol_items(data):
                            uid = resolve_pugongying_platform_uid(item)
                            if not uid:
                                continue
                            from_search_api = True
                            if uid in api_authors:
                                api_authors[uid] = merge_author_items(api_authors[uid], item)
                            else:
                                api_authors[uid] = item
                    except Exception:
                        pass

                page.on("response", on_response)
                search_url = PUGONGYING_SEARCH_URL.format(keyword=quote(keyword))
                page.goto(search_url, wait_until="domcontentloaded", timeout=settings.PLAYWRIGHT_TIMEOUT)
                page.wait_for_timeout(settings.PLAYWRIGHT_WAIT_AFTER_SEARCH)

                if not self._is_logged_in(page):
                    raise RuntimeError(
                        "蒲公英未登录或 Cookie 已过期。请在工作台配置蒲公英登录态"
                    )

                for _ in range(max(settings.PLAYWRIGHT_MAX_SCROLLS, 0)):
                    page.evaluate("window.scrollBy(0, window.innerHeight)")
                    page.wait_for_timeout(1200)

                dom_items = self._parse_dom(page)
                if api_authors:
                    authors = dict(api_authors)
                else:
                    for item in dom_items:
                        uid = resolve_pugongying_platform_uid(item)
                        if not uid:
                            continue
                        authors[uid] = merge_author_items(authors.get(uid, {}), item)

                for item in dom_items:
                    uid = resolve_pugongying_platform_uid(item)
                    if uid and uid in authors:
                        authors[uid] = merge_author_items(authors[uid], item)

                if not authors and api_authors:
                    for uid, item in api_authors.items():
                        authors[uid] = item

                if settings.PLAYWRIGHT_DETAIL_ENRICH_MAX > 0 and authors:
                    self._enrich_from_detail_pages(
                        page, authors, max_visits=settings.PLAYWRIGHT_DETAIL_ENRICH_MAX
                    )
            except Exception as exc:
                shot = _save_failure_screenshot(page, keyword)
                if shot:
                    raise RuntimeError(f"{exc}（截图: {shot}）") from exc
                raise
            finally:
                context.close()
                browser.close()

        results = self._to_raw_influencers(
            keyword,
            list(authors.values()),
            filters,
            require_keyword_match=bool((keyword or "").strip()) and not from_search_api,
        )
        logger.info("Pugongying collect done: keyword=%s, count=%d", keyword, len(results))

        if not results:
            raise RuntimeError(
                f"蒲公英未采集到与关键词「{keyword}」相关的博主，请检查关键词或登录态是否有效"
            )

        return results[: filters.limit]

    def _create_context(self, browser):
        kwargs: dict[str, Any] = {
            "viewport": {"width": 1440, "height": 900},
            "user_agent": settings.PLAYWRIGHT_USER_AGENT,
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
        }

        storage_path = Path(settings.PUGONGYING_STORAGE_STATE)
        if storage_path.exists():
            logger.info("Loading Pugongying storage state: %s", storage_path)
            context = browser.new_context(storage_state=str(storage_path), **kwargs)
        else:
            context = browser.new_context(**kwargs)
            cookies = _load_cookies()
            if cookies:
                context.add_cookies(cookies)

        context.set_extra_http_headers(
            {
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": "https://pgy.xiaohongshu.com/",
            }
        )
        return context

    @staticmethod
    def _is_logged_in(page) -> bool:
        url = page.url.lower()
        if "login" in url or "passport" in url:
            return False
        indicators = [
            "text=找博主",
            "text=蒲公英",
            "text=笔记博主",
            "text=退出登录",
            '[class*="kol"]',
        ]
        for sel in indicators:
            try:
                if page.locator(sel).first.is_visible(timeout=2000):
                    return True
            except Exception:
                continue
        return "pgy.xiaohongshu.com" in url and "login" not in url

    @staticmethod
    def _perform_search(page, keyword: str) -> None:
        search_selectors = [
            'input[placeholder*="搜索"]',
            'input[placeholder*="博主"]',
            'input[placeholder*="关键词"]',
            'input[type="search"]',
            ".search-input input",
            '[class*="search"] input',
        ]
        for selector in search_selectors:
            try:
                locator = page.locator(selector).first
                if locator.is_visible(timeout=2000):
                    locator.click()
                    locator.fill(keyword)
                    locator.press("Enter")
                    logger.info("Pugongying search via: %s", selector)
                    page.wait_for_timeout(settings.PLAYWRIGHT_WAIT_AFTER_SEARCH)
                    return
            except Exception:
                continue

        page.goto(PUGONGYING_SEARCH_URL.format(keyword=quote(keyword)), wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

    @staticmethod
    def _search_applied(page, keyword: str) -> bool:
        keyword = (keyword or "").strip()
        if not keyword:
            return True
        url = page.url
        if keyword in url or quote(keyword) in url:
            return True
        search_selectors = [
            'input[placeholder*="搜索"]',
            'input[placeholder*="博主"]',
            'input[placeholder*="关键词"]',
            'input[type="search"]',
            ".search-input input",
            '[class*="search"] input',
        ]
        for selector in search_selectors:
            try:
                value = page.locator(selector).first.input_value(timeout=1000)
                if keyword in (value or ""):
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _parse_dom(page) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        card_selectors = [
            '[class*="kol-card"]',
            '[class*="blogger-card"]',
            '[class*="creator-card"]',
            '[class*="kol"] [class*="item"]',
            '[class*="list"] [class*="row"]',
        ]
        for selector in card_selectors:
            cards = page.query_selector_all(selector)
            if not cards:
                continue
            for card in cards[:50]:
                try:
                    text = card.inner_text()
                    if not text.strip():
                        continue
                    dom_fields = parse_dom_text_fields(text)
                    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
                    nickname = lines[0] if lines else ""
                    follower_count = _parse_follower_from_text(text)
                    href = None
                    try:
                        link = card.query_selector("a[href]")
                        if link:
                            href = link.get_attribute("href")
                    except Exception:
                        pass

                    kol_id = None
                    if href:
                        match = re.search(r"/kol/([a-zA-Z0-9]+)", href)
                        if match:
                            kol_id = match.group(1)
                        match = re.search(r"user/profile/([a-zA-Z0-9]+)", href)
                        if match:
                            kol_id = match.group(1)

                    if nickname:
                        item: dict[str, Any] = {
                            "nickname": nickname,
                            "follower_count": follower_count,
                            "_dom": True,
                            **dom_fields,
                        }
                        if kol_id:
                            item["userId"] = kol_id
                        if href and href.startswith("http"):
                            item["homepage"] = href
                        items.append(item)
                except Exception:
                    continue
            if items:
                break
        return items

    @staticmethod
    def _enrich_from_detail_pages(page, authors: dict[str, dict[str, Any]], max_visits: int = 10) -> None:
        visited = 0
        for uid, item in list(authors.items())[:max_visits * 2]:
            if visited >= max_visits:
                break
            parsed = parse_pugongying_item(item)
            if parsed.get("profile_url") and parsed.get("engagement_rate") is not None:
                continue
            detail_url = build_pugongying_kol_url(uid) or parsed.get("pgy_homepage")
            if not detail_url:
                continue
            try:
                page.goto(detail_url, wait_until="domcontentloaded", timeout=settings.PLAYWRIGHT_TIMEOUT)
                page.wait_for_timeout(1800)
                visited += 1
            except Exception:
                logger.debug("Pugongying detail enrich failed: %s", uid, exc_info=True)

    def _to_raw_influencers(
        self,
        keyword: str,
        items: list[dict[str, Any]],
        filters: SearchFilters,
        *,
        require_keyword_match: bool = True,
    ) -> list[RawInfluencer]:
        results: list[RawInfluencer] = []
        seen_uids: set[str] = set()
        for item in items:
            raw = self._map_item(keyword, item)
            if not raw or raw.platform_uid in seen_uids:
                continue
            if require_keyword_match and not passes_keyword_match(
                keyword, raw.nickname, raw.matched_tags, raw.extra_data
            ):
                continue
            seen_uids.add(raw.platform_uid)
            if passes_search_filters(raw, filters):
                results.append(raw)
        results.sort(key=lambda x: x.match_score, reverse=True)
        return results

    def _map_item(self, keyword: str, item: dict[str, Any]) -> RawInfluencer | None:
        platform_uid = resolve_pugongying_platform_uid(item)
        nickname = pick_display_nickname(item, "xiaohongshu") or str(_pick(item, NICKNAME_KEYS) or "")
        if not platform_uid:
            return None

        tags = _pick(item, TAG_KEYS) or []
        if isinstance(tags, list):
            tag_names = [t.get("name", t) if isinstance(t, dict) else str(t) for t in tags if t]
        else:
            tag_names = []

        extra = {
            k: v
            for k, v in item.items()
            if k not in KOL_ID_KEYS + NICKNAME_KEYS + FOLLOWER_KEYS + AVATAR_KEYS
        }
        if item.get("_dom"):
            extra["source_type"] = "dom_fallback"

        pgy_raw = {k: v for k, v in extra.items() if not str(k).startswith("_")}
        parsed = parse_pugongying_item({**item, "pugongying_raw": pgy_raw})
        for style in parsed.get("content_styles") or []:
            if style and style not in tag_names:
                tag_names.append(style)

        mcn_name = extract_mcn_name({**item, "xingtu_raw": pgy_raw}) or parsed.get("mcn_name")
        profile_url = choose_best_profile_url(parsed, {**item, "pugongying_raw": pgy_raw})
        profile_url = resolve_collected_profile_url(
            "xiaohongshu",
            platform_uid,
            profile_url,
            extra_data={"parsed": parsed, "pugongying_raw": pgy_raw},
        )
        engagement_rate = parsed.get("engagement_rate")
        if engagement_rate is None:
            engagement_rate = _normalize_engagement_rate(
                item.get("engagement_rate") or item.get("interact_rate")
            )

        extra_data: dict[str, Any] = {
            "parsed": parsed,
            "quote_min": item.get("quote_min") or item.get("price_min"),
            "quote_max": item.get("quote_max") or item.get("price_max"),
            "pugongying_raw": pgy_raw,
        }
        if mcn_name:
            extra_data["mcn_name"] = mcn_name

        match_score = calc_keyword_match_score(keyword, nickname, tag_names, extra_data)

        return RawInfluencer(
            platform="xiaohongshu",
            platform_uid=platform_uid,
            nickname=nickname,
            avatar_url=_pick(item, AVATAR_KEYS),
            profile_url=profile_url,
            follower_count=_to_int(_pick(item, FOLLOWER_KEYS)),
            engagement_rate=engagement_rate,
            avg_views=parsed.get("avg_views"),
            source="pugongying",
            matched_tags=tag_names[:10],
            match_score=match_score,
            extra_data=extra_data,
        )


def _load_cookies() -> list[dict]:
    cookies: list[dict] = []
    cookie_file = Path(settings.PUGONGYING_COOKIE_FILE)
    if cookie_file.exists():
        with open(cookie_file, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data

    cookie_str = settings.PUGONGYING_COOKIE or settings.XIAOHONGSHU_COOKIE
    if not cookie_str:
        return cookies

    for domain in (".xiaohongshu.com", ".pgy.xiaohongshu.com"):
        for part in cookie_str.split(";"):
            part = part.strip()
            if "=" in part:
                name, value = part.split("=", 1)
                cookies.append(
                    {
                        "name": name.strip(),
                        "value": value.strip(),
                        "domain": domain,
                        "path": "/",
                    }
                )
    return cookies


def _pick(data: dict, keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def _extract_kol_items(data: Any, depth: int = 0) -> list[dict]:
    if depth > 10:
        return []
    results: list[dict] = []
    if isinstance(data, dict):
        if _looks_like_kol(data):
            results.append(data)
        for value in data.values():
            results.extend(_extract_kol_items(value, depth + 1))
    elif isinstance(data, list):
        for item in data:
            results.extend(_extract_kol_items(item, depth + 1))
    return results


def _looks_like_kol(data: dict) -> bool:
    has_id = any(k in data for k in KOL_ID_KEYS)
    has_name = any(k in data for k in NICKNAME_KEYS)
    has_metric = any(k in data for k in FOLLOWER_KEYS + ("interact_rate", "engagement_rate"))
    return has_id and (has_name or has_metric)


def _to_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).replace(",", "").strip()
    multiplier = 1
    if "万" in text:
        multiplier = 10000
        text = text.replace("万", "")
    if "w" in text.lower():
        multiplier = 10000
        text = re.sub(r"[wW]", "", text)
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return 0


def _normalize_engagement_rate(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().replace("%", "")
        try:
            value = float(text)
        except ValueError:
            return None
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return None
    if rate > 1:
        rate = rate / 100
    if rate < 0 or rate > 1:
        return None
    return round(rate, 4)


def _parse_follower_from_text(text: str) -> int:
    match = re.search(r"([\d.]+)\s*万?\s*粉丝", text)
    if match:
        num = float(match.group(1))
        return int(num * 10000) if "万" in text[match.start() : match.end() + 2] else int(num)
    match = re.search(r"粉丝\s*([\d,]+)", text)
    if match:
        return _to_int(match.group(1))
    return 0


def _calc_match_score(keyword: str, nickname: str, tags: list[str]) -> float:
    return calc_keyword_match_score(keyword, nickname, tags)
