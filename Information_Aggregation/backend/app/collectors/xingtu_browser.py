"""星图 Playwright 自动化采集器"""

import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.collectors.base import RawInfluencer, SearchFilters
from app.config import settings
from app.constants.xingtu_filters import PAGE_FILTER_LABELS
from app.collectors.filter_utils import passes_search_filters
from app.utils.mcn_utils import extract_mcn_name
from app.utils.collector_uid import (
    normalize_xingtu_authors,
    pick_display_nickname,
    resolve_xingtu_platform_uid,
)
from app.utils.keyword_match import calc_keyword_match_score, passes_keyword_match
from app.utils.xingtu_fields import (
    build_xingtu_homepage,
    choose_best_profile_url,
    merge_author_items,
    needs_detail_enrichment,
    parse_dom_text_fields,
    parse_xingtu_item,
    _pick_star_id,
    _normalize_count,
)

logger = logging.getLogger(__name__)

XINGTU_MARKET_URL = "https://www.xingtu.cn/ad/creator/market"
XINGTU_SEARCH_URL = "https://www.xingtu.cn/ad/creator/market?keyword={keyword}"

AUTHOR_ID_KEYS = ("author_id", "star_id", "uid", "user_id", "core_user_id")
NICKNAME_KEYS = ("nick_name", "nickname", "author_name", "name")
FOLLOWER_KEYS = ("follower_count", "follower", "fans_num", "fans_count", "follower_num")
AVATAR_KEYS = ("avatar_uri", "avatar_url", "avatar", "head_image")
TAG_KEYS = ("tags", "tag_list", "content_tags", "category_tags")
AVG_PLAY_KEYS = ("avg_play", "avg_play_count", "play_count_avg", "average_play")

INTERCEPT_URL_KEYWORDS = (
    "search_for_author_square",
    "search_for_author",
)

EXCLUDE_URL_KEYWORDS = (
    "recommend",
    "demander_get",
    "/u/login",
    "/u/api/demander",
    "get_collaboration",
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

        filename = f"xingtu_fail_{datetime.now():%Y%m%d_%H%M%S}_{safe_kw}.png"
        path = log_dir / filename
        page.screenshot(path=str(path), full_page=True)
        return str(path)
    except Exception:
        logger.exception("Failed to save screenshot")
        return None


class XingtuBrowserCollector:
    """通过 Playwright 自动化操作星图达人广场，拦截 API 响应获取达人数据"""

    def search(self, keyword: str, filters: SearchFilters) -> list[RawInfluencer]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("请先安装 Playwright: pip install playwright && playwright install chromium") from exc

        logger.info("Xingtu Playwright collect start: keyword=%s", keyword)
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
                    if "xingtu.cn" not in url:
                        return
                    if any(k in url for k in EXCLUDE_URL_KEYWORDS):
                        return
                    if not any(k in url for k in INTERCEPT_URL_KEYWORDS):
                        return
                    try:
                        data = response.json()
                        for item in _extract_author_items(data):
                            uid = resolve_xingtu_platform_uid(item)
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
                search_url = XINGTU_SEARCH_URL.format(keyword=quote(keyword))
                page.goto(search_url, wait_until="domcontentloaded", timeout=settings.PLAYWRIGHT_TIMEOUT)
                page.wait_for_timeout(settings.PLAYWRIGHT_WAIT_AFTER_SEARCH)

                if not self._is_logged_in(page):
                    raise RuntimeError(
                        "星图未登录或 Cookie 已过期。请在工作台配置星图登录态"
                    )

                if self._has_active_filters(filters):
                    self._apply_page_filters(page, filters)
                    page.wait_for_timeout(settings.PLAYWRIGHT_WAIT_AFTER_SEARCH)

                for _ in range(max(settings.PLAYWRIGHT_MAX_SCROLLS, 0)):
                    page.evaluate("window.scrollBy(0, window.innerHeight)")
                    page.wait_for_timeout(1200)

                table_items = self._parse_market_table(page)
                if not table_items:
                    table_items = self._parse_result_cards(page)

                if api_authors:
                    authors = {uid: {**item, "_from_search_api": True} for uid, item in api_authors.items()}
                else:
                    for item in table_items:
                        uid = resolve_xingtu_platform_uid(item)
                        nickname = pick_display_nickname(item, "douyin")
                        if not uid and nickname:
                            continue
                        if not uid:
                            continue
                        authors[uid] = merge_author_items(authors.get(uid, {}), item)

                for item in table_items:
                    uid = resolve_xingtu_platform_uid(item)
                    if uid and uid in authors:
                        authors[uid] = merge_author_items(authors[uid], item)

                if not authors and api_authors:
                    for uid, item in api_authors.items():
                        authors[uid] = item

                if settings.PLAYWRIGHT_DETAIL_ENRICH_MAX > 0 and authors:
                    self._enrich_from_detail_pages(
                        page, authors, filters.limit, max_visits=settings.PLAYWRIGHT_DETAIL_ENRICH_MAX
                    )
            except Exception as exc:
                shot = _save_failure_screenshot(page, keyword)
                if shot:
                    logger.error("Saved failure screenshot: %s", shot)
                    raise RuntimeError(f"{exc}（截图: {shot}）") from exc
                raise
            finally:
                context.close()
                browser.close()

        authors = normalize_xingtu_authors(authors)
        captured = list(authors.values())
        has_keyword = bool((keyword or "").strip())
        results = self._to_raw_influencers(
            keyword,
            captured,
            filters,
            require_keyword_match=has_keyword and not from_search_api,
        )
        logger.info("Xingtu Playwright collect done: keyword=%s, count=%d", keyword, len(results))

        if not results:
            raise RuntimeError(
                f"星图未采集到与关键词「{keyword}」相关的达人，请检查关键词或 Cookie 是否有效"
            )

        return results[: filters.limit]

    def _create_context(self, browser):
        kwargs: dict[str, Any] = {
            "viewport": {"width": 1440, "height": 900},
            "user_agent": settings.PLAYWRIGHT_USER_AGENT,
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
        }

        storage_path = Path(settings.XINGTU_STORAGE_STATE)
        if storage_path.exists():
            logger.info("Loading Xingtu storage state: %s", storage_path)
            context = browser.new_context(storage_state=str(storage_path), **kwargs)
        else:
            context = browser.new_context(**kwargs)
            cookies = _load_cookies()
            if cookies:
                context.add_cookies(cookies)

        context.set_extra_http_headers(
            {
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": "https://www.xingtu.cn/",
            }
        )
        return context

    @staticmethod
    def _is_logged_in(page) -> bool:
        url = page.url.lower()
        if "login" in url or "passport" in url:
            return False
        # 已登录页面通常有用户菜单或达人列表
        indicators = [
            "text=达人广场",
            "text=创作者市场",
            "text=退出登录",
            '[class*="creator"]',
            '[class*="market"]',
        ]
        for sel in indicators:
            try:
                if page.locator(sel).first.is_visible(timeout=2000):
                    return True
            except Exception:
                continue
        return "market" in url or "creator" in url

    @staticmethod
    def _has_active_filters(filters: SearchFilters) -> bool:
        from dataclasses import fields

        for field in fields(filters):
            if field.name == "limit":
                continue
            value = getattr(filters, field.name, None)
            if value not in (None, "", [], {}):
                return True
        return False

    @staticmethod
    def _perform_search(page, keyword: str) -> None:
        search_selectors = [
            'input[placeholder*="搜索"]',
            'input[placeholder*="达人"]',
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
                    logger.info("Search submitted via selector: %s", selector)
                    page.wait_for_timeout(settings.PLAYWRIGHT_WAIT_AFTER_SEARCH)
                    return
            except Exception:
                continue

        # 备用：带关键词 URL
        page.goto(XINGTU_SEARCH_URL.format(keyword=quote(keyword)), wait_until="domcontentloaded")
        page.wait_for_timeout(settings.PLAYWRIGHT_WAIT_AFTER_SEARCH)

    @staticmethod
    def _parse_result_cards(page) -> list[dict[str, Any]]:
        """解析非 table 布局的达人卡片列表"""
        try:
            rows_data = page.evaluate(
                """() => {
                const results = [];
                const cardSelectors = [
                    '[class*="author"]',
                    '[class*="creator"]',
                    '[class*="star-card"]',
                    '[class*="market"] [class*="item"]',
                    '[class*="list"] [class*="row"]',
                ];
                const seen = new Set();
                const skipWords = ['达人清单', '我的清单', '观众画像', '达人信息', '合作', '筛选', '排序'];
                for (const selector of cardSelectors) {
                    const cards = document.querySelectorAll(selector);
                    for (const card of cards) {
                        const text = (card.innerText || '').trim();
                        if (!text || text.length < 4) continue;
                        const lines = text.split('\\n').map((s) => s.trim()).filter(Boolean);
                        if (!lines.length) continue;
                        const nickname = lines[0];
                        if (!nickname || seen.has(nickname)) continue;
                        if (skipWords.some((w) => nickname.includes(w))) continue;
                        if (/^[¥￥]/.test(nickname) || /^\\d+$/.test(nickname)) continue;
                        const link = card.querySelector('a[href*="author-homepage"], a[href*="/creator/"]');
                        const item = { nick_name: nickname };
                        if (link) {
                            const href = link.getAttribute('href') || '';
                            const match = href.match(/(\\d{11,20})/);
                            if (match) item.author_id = match[1];
                        }
                        if (!item.author_id && !/粉丝|万|互动率|预期播放/.test(text)) continue;
                        const followerMatch = text.match(/粉丝[：:\\s]*([\\d.,]+万?)/);
                        if (followerMatch) item.follower_count = followerMatch[1];
                        const playMatch = text.match(/预期播放[量]*[：:\\s]*([\\d.,]+万?)/);
                        if (playMatch) item.expect_play_count = playMatch[1];
                        const rateMatch = text.match(/互动率[：:\\s]*([\\d.]+%?)/);
                        if (rateMatch) item.interact_rate = rateMatch[1];
                        seen.add(nickname);
                        results.push(item);
                    }
                    if (results.length >= 5) break;
                }
                return results;
            }"""
            )
            return rows_data if isinstance(rows_data, list) else []
        except Exception:
            logger.debug("Result card parse failed", exc_info=True)
            return []

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
            'input[placeholder*="达人"]',
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

    def _apply_page_filters(self, page, filters: SearchFilters) -> None:
        """在星图页面上点击对应筛选项（默认「不限」则跳过）"""
        applied: list[str] = []

        for field_key, row_label in PAGE_FILTER_LABELS.items():
            value = getattr(filters, field_key, None)
            if value and self._click_filter_tag(page, row_label, str(value)):
                applied.append(f"{row_label}={value}")
                page.wait_for_timeout(800)

        if filters.theme_tags:
            for tag in filters.theme_tags:
                if self._click_checkbox_option(page, tag):
                    applied.append(f"主题={tag}")
                    page.wait_for_timeout(500)

        if applied:
            logger.info("Applied Xingtu page filters: %s", ", ".join(applied))
            page.wait_for_timeout(1500)

    @staticmethod
    def _click_filter_tag(page, row_label: str, option: str) -> bool:
        if not option or option == "不限":
            return False
        try:
            label = page.get_by_text(row_label, exact=True).first
            if not label.is_visible(timeout=1500):
                return False
            row = label.locator(
                "xpath=ancestor::*[contains(@class,'filter') or contains(@class,'row') "
                "or contains(@class,'item') or contains(@class,'line')][1]"
            )
            tag = row.get_by_text(option, exact=True).first
            if tag.is_visible(timeout=1500):
                tag.click()
                return True
        except Exception:
            pass
        try:
            tag = page.get_by_text(option, exact=True).first
            if tag.is_visible(timeout=1000):
                tag.click()
                return True
        except Exception:
            pass
        return False

    @staticmethod
    def _click_checkbox_option(page, label: str) -> bool:
        try:
            item = page.get_by_text(label, exact=True).first
            if item.is_visible(timeout=1500):
                item.click()
                return True
        except Exception:
            pass
        return False

    @staticmethod
    def _enrich_from_detail_pages(
        page,
        authors: dict[str, dict[str, Any]],
        limit: int,
        max_visits: int = 12,
    ) -> None:
        """访问星图达人主页，补全联系方式、互动率等详情字段"""
        candidates: list[tuple[str, dict[str, Any]]] = []
        for uid, item in authors.items():
            parsed = parse_xingtu_item(item)
            if needs_detail_enrichment(parsed):
                candidates.append((uid, item))

        visited = 0
        for uid, item in candidates[:max_visits]:
            if visited >= max_visits or len(authors) >= limit * 2:
                break
            star_id = _pick_star_id(item) or (
                uid if uid and str(uid).isdigit() and len(str(uid)) >= 11 else None
            )
            if not star_id:
                continue
            detail_url = build_xingtu_homepage(star_id)
            if not detail_url:
                continue
            try:
                page.goto(detail_url, wait_until="domcontentloaded", timeout=settings.PLAYWRIGHT_TIMEOUT)
                page.wait_for_timeout(1800)
                visited += 1
            except Exception:
                logger.debug("Detail page enrich failed for %s", star_id, exc_info=True)

    @staticmethod
    def _parse_market_table(page) -> list[dict[str, Any]]:
        """从达人广场列表表格解析达人类型、预期播放量、完播率、成交率等列"""
        try:
            rows_data = page.evaluate(
                """() => {
                const HEADER_MAP = {
                    '达人类型': 'creator_type',
                    '粉丝数': 'follower_count',
                    '预期播放量': 'expect_play_count',
                    '互动率': 'interact_rate',
                    '完播率': 'completion_rate',
                    '成交率': 'deal_rate',
                };
                const results = [];
                const tables = document.querySelectorAll('table');
                for (const table of tables) {
                    let headerCells = table.querySelectorAll('thead th, thead td');
                    if (!headerCells.length) {
                        const firstRow = table.querySelector('tr');
                        if (firstRow) headerCells = firstRow.querySelectorAll('th, td');
                    }
                    const headers = Array.from(headerCells).map((c) => c.innerText.trim()).filter(Boolean);
                    if (!headers.some((h) => h.includes('粉丝') || h.includes('互动率') || h.includes('预期播放'))) {
                        continue;
                    }
                    const colMap = {};
                    headers.forEach((header, index) => {
                        for (const [label, key] of Object.entries(HEADER_MAP)) {
                            if (header === label || header.includes(label)) {
                                colMap[index] = key;
                            }
                        }
                    });
                    const bodyRows = table.querySelectorAll('tbody tr');
                    const rows = bodyRows.length ? bodyRows : Array.from(table.querySelectorAll('tr')).slice(1);
                    for (const row of rows) {
                        const cells = row.querySelectorAll('td');
                        if (cells.length < 3) continue;
                        const item = {};
                        cells.forEach((cell, index) => {
                            const key = colMap[index];
                            if (key) item[key] = cell.innerText.trim();
                        });
                        const firstText = cells[0]?.innerText?.trim().split('\\n').filter(Boolean) || [];
                        if (firstText.length) item.nick_name = firstText[0];
                        const link = cells[0]?.querySelector('a[href*="author-homepage"], a[href*="/creator/"]');
                        if (link) {
                            const href = link.getAttribute('href') || '';
                            const match = href.match(/(\\d{11,20})/);
                            if (match) item.author_id = match[1];
                        }
                        if (Object.keys(item).length > 1) results.push(item);
                    }
                }
                return results;
            }"""
            )
            return rows_data if isinstance(rows_data, list) else []
        except Exception:
            logger.debug("Market table parse failed", exc_info=True)
            return []

    @staticmethod
    def _parse_dom(page) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        card_selectors = [
            '[class*="author-card"]',
            '[class*="creator-card"]',
            '[class*="star-card"]',
            '[class*="market"] [class*="item"]',
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
                    mcn_match = re.search(r"MCN[：:\s]+([^\n\r]+)", text, re.I)
                    href = None
                    try:
                        link = card.query_selector("a[href]")
                        if link:
                            href = link.get_attribute("href")
                    except Exception:
                        pass
                    if nickname:
                        item: dict[str, Any] = {
                            "nick_name": nickname,
                            "follower_count": follower_count,
                            "_dom": True,
                            **dom_fields,
                        }
                        if mcn_match:
                            item["mcn_name"] = mcn_match.group(1).strip()
                        if href and href.startswith("http"):
                            item["homepage"] = href
                        items.append(item)
                except Exception:
                    continue
            if items:
                break
        return items

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
        platform_uid = resolve_xingtu_platform_uid(item)
        nickname = pick_display_nickname(item, "douyin") or str(_pick(item, NICKNAME_KEYS) or "")
        if not platform_uid:
            return None

        tags = _pick(item, TAG_KEYS) or []
        if isinstance(tags, list):
            tag_names = [t.get("name", t) if isinstance(t, dict) else str(t) for t in tags if t]
        else:
            tag_names = []

        follower_count = _to_int(_pick(item, FOLLOWER_KEYS))
        if not follower_count:
            follower_count = _normalize_count(item.get("follower_count")) or 0

        extra = {
            k: v
            for k, v in item.items()
            if k not in AUTHOR_ID_KEYS + NICKNAME_KEYS + FOLLOWER_KEYS + AVATAR_KEYS
        }
        if item.get("_dom"):
            extra["source_type"] = "dom_fallback"

        xingtu_raw = {k: v for k, v in extra.items() if not str(k).startswith("_")}
        mcn_name = extract_mcn_name({**item, "xingtu_raw": xingtu_raw})
        parsed = parse_xingtu_item({**item, "xingtu_raw": xingtu_raw})
        for style in parsed.get("content_styles") or []:
            if style and style not in tag_names:
                tag_names.append(style)

        profile_url = choose_best_profile_url(parsed, {**item, "xingtu_raw": xingtu_raw})
        engagement_rate = parsed.get("engagement_rate")
        if engagement_rate is None:
            engagement_rate = _normalize_engagement_rate(
                item.get("engagement_rate") or item.get("interact_rate")
            )
        avg_views = parsed.get("expected_play_count") or parsed.get("avg_views") or _to_int(
            _pick(item, AVG_PLAY_KEYS)
        )
        if not avg_views:
            avg_views = _normalize_count(item.get("expect_play_count"))

        extra_data: dict[str, Any] = {
            "parsed": parsed,
            "creator_type": parsed.get("creator_type"),
            "expected_play_count": parsed.get("expected_play_count") or avg_views,
            "completion_rate": parsed.get("completion_rate"),
            "deal_rate": parsed.get("deal_rate"),
            "recent_gmv": item.get("gmv_30d") or item.get("sale_amount"),
            "showcase_count": item.get("showcase_count") or item.get("product_count"),
            "quote_min": item.get("quote_min") or item.get("price_min"),
            "quote_max": item.get("quote_max") or item.get("price_max"),
            "xingtu_raw": xingtu_raw,
        }
        if mcn_name:
            extra_data["mcn_name"] = mcn_name

        match_score = calc_keyword_match_score(keyword, nickname, tag_names, extra_data)
        if item.get("_from_search_api") and match_score < 30:
            match_score = 30.0

        return RawInfluencer(
            platform="douyin",
            platform_uid=platform_uid,
            nickname=nickname,
            avatar_url=_pick(item, AVATAR_KEYS),
            profile_url=profile_url,
            follower_count=follower_count,
            engagement_rate=engagement_rate,
            avg_views=avg_views,
            source="xingtu",
            matched_tags=tag_names[:10],
            match_score=match_score,
            extra_data=extra_data,
        )


def _load_cookies() -> list[dict]:
    cookies: list[dict] = []

    cookie_file = Path(settings.XINGTU_COOKIE_FILE)
    if cookie_file.exists():
        with open(cookie_file, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data

    cookie_str = settings.XINGTU_COOKIE or settings.DOUYIN_COOKIE
    if not cookie_str:
        return cookies

    for domain in (".xingtu.cn", ".douyin.com"):
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


def _extract_author_items(data: Any, depth: int = 0) -> list[dict]:
    if depth > 10:
        return []
    results: list[dict] = []
    if isinstance(data, dict):
        if _looks_like_author(data):
            results.append(data)
        for value in data.values():
            results.extend(_extract_author_items(value, depth + 1))
    elif isinstance(data, list):
        for item in data:
            results.extend(_extract_author_items(item, depth + 1))
    return results


def _looks_like_author(data: dict) -> bool:
    has_id = any(k in data for k in AUTHOR_ID_KEYS)
    has_name = any(k in data for k in NICKNAME_KEYS)
    has_metric = any(
        k in data
        for k in FOLLOWER_KEYS
        + AVG_PLAY_KEYS
        + (
            "interact_rate",
            "engagement_rate",
            "interaction_rate",
            "expect_play_count",
            "completion_rate",
            "deal_rate",
            "creator_type",
        )
    )
    has_profile = any(k in data for k in ("homepage", "profile_url", "sec_uid", "contact_phone"))
    return has_id and (has_name or has_metric or has_profile)


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


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
