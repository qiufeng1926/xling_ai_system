"""星图 Playwright 自动化采集器"""

import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.collectors.base import RawInfluencer, SearchFilters
from app.config import settings
from app.constants.xingtu_filters import (
    PAGE_FILTER_CLICK,
    PAGE_FILTER_LABELS,
    PAGE_FILTER_SECTIONS,
    PAGE_FILTER_VALUE_ALIASES,
)
from app.collectors.filter_utils import passes_search_filters
from app.utils.mcn_utils import extract_mcn_name
from app.utils.collector_uid import (
    normalize_xingtu_authors,
    pick_display_nickname,
    resolve_xingtu_platform_uid,
)
from app.utils.collected_parsed import resolve_collected_profile_url
from app.utils.keyword_match import calc_keyword_match_score, passes_keyword_match
from app.utils.xingtu_fields import (
    build_xingtu_homepage,
    choose_best_profile_url,
    extract_star_id_from_profile_url,
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


def _is_author_search_response(url: str, status: int = 200) -> bool:
    if status != 200:
        return False
    url = url.lower()
    if "xingtu.cn" not in url:
        return False
    if any(k in url for k in EXCLUDE_URL_KEYWORDS):
        return False
    return any(k in url for k in INTERCEPT_URL_KEYWORDS)


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
        has_keyword = bool((keyword or "").strip())
        has_filters = self._has_active_filters(filters)
        will_prepare_page = has_keyword or has_filters
        max_pages = max(
            1,
            min(
                settings.PLAYWRIGHT_MAX_PAGES,
                (filters.limit + settings.PLAYWRIGHT_PAGE_SIZE - 1) // settings.PLAYWRIGHT_PAGE_SIZE + 1,
            ),
        )

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=settings.PLAYWRIGHT_HEADLESS,
                slow_mo=settings.PLAYWRIGHT_SLOW_MO,
            )
            context = self._create_context(browser)
            page = None
            api_authors: dict[str, dict[str, Any]] = {}
            capture_enabled = not will_prepare_page

            try:
                page = context.new_page()

                def on_response(response) -> None:
                    nonlocal from_search_api
                    if not capture_enabled:
                        return
                    if not _is_author_search_response(response.url, response.status):
                        return
                    content_type = response.headers.get("content-type", "")
                    if "json" not in content_type:
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
                page.goto(XINGTU_MARKET_URL, wait_until="domcontentloaded", timeout=settings.PLAYWRIGHT_TIMEOUT)
                page.wait_for_timeout(settings.PLAYWRIGHT_WAIT_AFTER_SEARCH)

                if not self._is_logged_in(page):
                    raise RuntimeError(
                        "星图未登录或 Cookie 已过期。请在工作台配置星图登录态"
                    )

                if has_keyword:
                    self._perform_search(page, keyword)

                if has_filters:
                    applied = self._apply_page_filters(page, filters)
                    if applied:
                        logger.info("Xingtu filters applied: %s", ", ".join(applied))

                if will_prepare_page:
                    self._wait_for_results_refresh(page)
                    page.wait_for_timeout(settings.PLAYWRIGHT_WAIT_AFTER_SEARCH)
                    api_authors.clear()
                    from_search_api = False
                    capture_enabled = True
                    logger.info("Xingtu API capture enabled after search/filters settled")
                    self._wait_for_filtered_results_api(page)

                self._scroll_to_results_area(page)
                self._collect_result_pages(page, api_authors, filters.limit, max_pages)

                if api_authors:
                    authors = {uid: {**item, "_from_search_api": True} for uid, item in api_authors.items()}
                else:
                    table_items = self._parse_market_table(page)
                    if not table_items:
                        table_items = self._parse_result_cards(page)
                    for item in table_items:
                        uid = resolve_xingtu_platform_uid(item)
                        if uid:
                            authors[uid] = merge_author_items(authors.get(uid, {}), item)

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
        page_filtered = from_search_api and (has_filters or has_keyword)
        results = self._to_raw_influencers(
            keyword,
            captured,
            filters,
            require_keyword_match=has_keyword and not from_search_api,
            skip_local_filters=page_filtered,
        )
        logger.info("Xingtu Playwright collect done: keyword=%s, count=%d", keyword, len(results))

        if len(results) < filters.limit:
            logger.warning(
                "Xingtu collected %d/%d requested (pages=%d, api_raw=%d)",
                len(results),
                filters.limit,
                max_pages,
                len(captured),
            )

        if not results:
            raise RuntimeError(
                f"星图未采集到与关键词/筛选匹配的达人，请检查条件或 Cookie 是否有效"
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
            'input[placeholder*="匹配关键词"]',
            'input[placeholder*="达人昵称"]',
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

        page.goto(XINGTU_SEARCH_URL.format(keyword=quote(keyword)), wait_until="domcontentloaded")
        page.wait_for_timeout(settings.PLAYWRIGHT_WAIT_AFTER_SEARCH)

    @staticmethod
    def _wait_for_results_refresh(page) -> None:
        page.wait_for_timeout(settings.PLAYWRIGHT_FILTER_WAIT)

    @staticmethod
    def _wait_for_filtered_results_api(page) -> None:
        """筛选/搜索完成后等待首屏达人列表 API，避免采集到准备阶段的无关数据"""
        try:
            with page.expect_response(
                lambda r: _is_author_search_response(r.url, r.status)
                and "json" in r.headers.get("content-type", ""),
                timeout=settings.PLAYWRIGHT_TIMEOUT,
            ):
                page.evaluate("window.scrollBy(0, Math.min(window.innerHeight, 600))")
            page.wait_for_timeout(settings.PLAYWRIGHT_FILTER_WAIT)
            logger.info("Xingtu filtered results API received")
        except Exception:
            logger.warning("Timed out waiting for filtered results API, fallback to DOM refresh wait")
            page.wait_for_timeout(settings.PLAYWRIGHT_FILTER_WAIT)

    @staticmethod
    def _scroll_to_results_area(page) -> None:
        """滚动到达人列表区域（筛选区下方）"""
        try:
            page.evaluate(
                """() => {
                const markers = ['找到', '达人信息', '代表视频', '已选条件'];
                for (const text of markers) {
                    const nodes = [...document.querySelectorAll('*')].filter(
                        (el) => el.childElementCount < 5 && (el.innerText || '').includes(text)
                    );
                    for (const node of nodes) {
                        const rect = node.getBoundingClientRect();
                        if (rect.top > 120 && rect.top < window.innerHeight * 2) {
                            node.scrollIntoView({ block: 'center', behavior: 'instant' });
                            return true;
                        }
                    }
                }
                window.scrollBy(0, window.innerHeight * 2);
                return false;
            }"""
            )
        except Exception:
            page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
        page.wait_for_timeout(1200)
        for _ in range(max(settings.PLAYWRIGHT_MAX_SCROLLS, 0)):
            page.evaluate("window.scrollBy(0, window.innerHeight)")
            page.wait_for_timeout(800)

    def _collect_result_pages(
        self,
        page,
        api_authors: dict[str, dict[str, Any]],
        limit: int,
        max_pages: int,
    ) -> None:
        target = limit + max(5, limit // 5)
        for page_idx in range(max_pages):
            before = len(api_authors)
            self._scroll_to_results_area(page)
            self._scroll_pagination_into_view(page)
            self._wait_for_results_refresh(page)
            after = len(api_authors)
            logger.info("Xingtu page %d: api authors=%d (+%d)", page_idx + 1, after, after - before)
            if len(api_authors) >= target:
                break
            if page_idx + 1 >= max_pages:
                break
            if not self._go_next_page(page, page_idx + 2):
                break

    @staticmethod
    def _scroll_pagination_into_view(page) -> None:
        try:
            page.evaluate(
                """() => {
                const pg = document.querySelector('.ant-pagination, [class*="pagination"]');
                if (pg) pg.scrollIntoView({ block: 'center', behavior: 'instant' });
            }"""
            )
            page.wait_for_timeout(500)
        except Exception:
            pass

    @staticmethod
    def _go_next_page(page, target_page: int | None = None) -> bool:
        """翻到下一页（优先点页码，其次点下一页按钮）"""
        XingtuBrowserCollector._scroll_pagination_into_view(page)

        if target_page and target_page > 1:
            for selector in (
                f'.ant-pagination-item[title="{target_page}"]',
                f'li[title="{target_page}"]',
            ):
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=1500):
                        btn.click()
                        page.wait_for_timeout(settings.PLAYWRIGHT_FILTER_WAIT)
                        return True
                except Exception:
                    continue
            try:
                clicked = page.get_by_text(str(target_page), exact=True).first
                if clicked.is_visible(timeout=1000):
                    clicked.click()
                    page.wait_for_timeout(settings.PLAYWRIGHT_FILTER_WAIT)
                    return True
            except Exception:
                pass

        selectors = [
            ".ant-pagination-next:not(.ant-pagination-disabled)",
            '[class*="pagination"] [class*="next"]:not([class*="disabled"])',
            'button:has-text("下一页")',
            'li[title="下一页"]:not([class*="disabled"])',
        ]
        for selector in selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=1500) and btn.is_enabled():
                    btn.click()
                    page.wait_for_timeout(settings.PLAYWRIGHT_FILTER_WAIT)
                    return True
            except Exception:
                continue
        try:
            clicked = page.evaluate(
                """() => {
                const candidates = [...document.querySelectorAll('button, li, a, span')].filter((el) => {
                    const text = (el.innerText || '').trim();
                    const cls = el.className || '';
                    if (/disabled/.test(cls)) return false;
                    return text === '下一页' || text === '>' || text === '›';
                });
                if (!candidates.length) return false;
                candidates[0].click();
                return true;
            }"""
            )
            if clicked:
                page.wait_for_timeout(settings.PLAYWRIGHT_FILTER_WAIT)
                return True
        except Exception:
            pass
        return False

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
                            const match = href.match(/author-homepage\\/(?:douyin-video|abstract|live|short-video)\\/(\\d{11,20})/i)
                                || href.match(/(\\d{11,20})/);
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

    @staticmethod
    def _scroll_to_filter_area(page) -> None:
        try:
            page.evaluate(
                """() => {
                for (const text of ['合作诉求', '匹配度', '达人类型', '营销目标']) {
                    const node = [...document.querySelectorAll('td.filter-list-group__title, .underline-tooltip')].find(
                        (el) => (el.innerText || '').trim() === text
                    );
                    if (node) {
                        node.scrollIntoView({ block: 'center', behavior: 'instant' });
                        return true;
                    }
                }
                window.scrollTo(0, 0);
                return false;
            }"""
            )
        except Exception:
            pass
        page.wait_for_timeout(800)

    @staticmethod
    def _resolve_page_filter_value(field_key: str, value: Any) -> str:
        text = str(value)
        return PAGE_FILTER_VALUE_ALIASES.get(field_key, {}).get(text, text)

    @staticmethod
    def _scroll_to_filter_section(page, section: str | None) -> None:
        if not section:
            XingtuBrowserCollector._scroll_to_filter_area(page)
            return
        try:
            title = page.locator("td.filter-list-group__title", has_text=section).first
            title.scroll_into_view_if_needed(timeout=3000)
            page.wait_for_timeout(400)
        except Exception:
            XingtuBrowserCollector._scroll_to_filter_area(page)

    def _apply_page_filters(self, page, filters: SearchFilters) -> list[str]:
        """在星图页面上点击筛选项，覆盖行内标签、下拉与粉丝画像弹层"""
        self._scroll_to_filter_area(page)
        applied: list[str] = []
        failed: list[str] = []

        for field_key, click_cfg in PAGE_FILTER_CLICK.items():
            value = getattr(filters, field_key, None)
            if not value:
                continue
            if click_cfg.get("type") == "fans_panel":
                continue

            display_value = self._resolve_page_filter_value(field_key, value)
            row_label = PAGE_FILTER_LABELS.get(field_key, field_key)
            section = click_cfg.get("section") or PAGE_FILTER_SECTIONS.get(field_key)
            self._scroll_to_filter_section(page, section)

            click_type = click_cfg.get("type", "inline")
            if click_type == "inline":
                clicked = self._click_inline_filter(page, click_cfg["line"], display_value, section)
            elif click_type == "dropdown":
                clicked = self._click_dropdown_filter(
                    page,
                    click_cfg["parent_line"],
                    click_cfg["dropdown"],
                    display_value,
                    section,
                )
            elif click_type == "quote":
                clicked = self._click_quote_duration(page, display_value)
            else:
                clicked = False

            if clicked:
                applied.append(f"{row_label}={display_value}")
                page.wait_for_timeout(settings.PLAYWRIGHT_FILTER_WAIT)
            else:
                failed.append(f"{row_label}={display_value}")

        fans_options: list[tuple[str, str]] = []
        if filters.follower_gender:
            fans_options.append(
                (
                    PAGE_FILTER_LABELS["follower_gender"],
                    self._resolve_page_filter_value("follower_gender", filters.follower_gender),
                )
            )
        if filters.follower_age:
            fans_options.append(
                (
                    PAGE_FILTER_LABELS["follower_age"],
                    self._resolve_page_filter_value("follower_age", filters.follower_age),
                )
            )
        if fans_options:
            self._scroll_to_filter_section(page, "匹配度")
            if self._click_fans_panel_options(page, [opt for _, opt in fans_options]):
                for row_label, display_value in fans_options:
                    applied.append(f"{row_label}={display_value}")
                page.wait_for_timeout(settings.PLAYWRIGHT_FILTER_WAIT)
            else:
                for row_label, display_value in fans_options:
                    failed.append(f"{row_label}={display_value}")

        if filters.theme_tags:
            self._scroll_to_filter_section(page, "主题推荐")
            for tag in filters.theme_tags:
                display_tag = self._resolve_page_filter_value("theme_tags", tag)
                if self._click_theme_tag(page, display_tag):
                    applied.append(f"主题={display_tag}")
                    page.wait_for_timeout(settings.PLAYWRIGHT_FILTER_WAIT)
                else:
                    failed.append(f"主题={display_tag}")

        if failed:
            logger.warning("Xingtu filters not applied on page: %s", ", ".join(failed))
        if applied:
            logger.info("Xingtu filters applied on page: %s", ", ".join(applied))
            self._scroll_to_results_area(page)
            active = self._read_active_filter_chips(page)
            if active:
                logger.info("Xingtu active filter chips: %s", ", ".join(active))
        return applied

    @staticmethod
    def _read_active_filter_chips(page) -> list[str]:
        try:
            chips = page.evaluate(
                """() => {
                const chips = [];
                const area = [...document.querySelectorAll('*')].find(
                    (el) => (el.innerText || '').includes('已选条件')
                );
                if (!area) return chips;
                const container = area.closest('div') || area.parentElement;
                if (!container) return chips;
                for (const el of container.querySelectorAll('span, div, label')) {
                    const t = (el.innerText || '').trim();
                    if (t && t.includes(':') && t.length < 40) chips.push(t);
                }
                return [...new Set(chips)];
            }"""
            )
            return chips if isinstance(chips, list) else []
        except Exception:
            return []

    @staticmethod
    def _filter_section_locator(page, section: str | None):
        if section:
            return page.locator("tr.filter-list-group").filter(has_text=section).first
        return page.locator("tr.filter-list-group").first

    @staticmethod
    def _click_inline_filter(page, line_label: str, option: str, section: str | None = None) -> bool:
        if not option or option == "不限":
            return False
        try:
            section_loc = XingtuBrowserCollector._filter_section_locator(page, section)
            line = section_loc.locator(".market-filter-wrapper--line").filter(has_text=line_label).first
            line.scroll_into_view_if_needed(timeout=3000)
            page.wait_for_timeout(300)
            for exact in (True, False):
                tag = line.get_by_text(option, exact=exact).first
                if tag.is_visible(timeout=1000):
                    tag.click()
                    logger.info("Clicked inline filter %s=%s", line_label, option)
                    return True
        except Exception:
            logger.debug("Inline filter click failed: %s=%s", line_label, option, exc_info=True)
        return False

    @staticmethod
    def _find_dropdown_in_line(parent, dropdown_label: str):
        for selector in (
            ".base-market-dropdown",
            ".xt-dropdown",
            ".star-select",
        ):
            dropdown = parent.locator(selector).filter(has_text=dropdown_label)
            if dropdown.count() > 0:
                return dropdown.last
        return parent.get_by_text(dropdown_label, exact=True).last

    @staticmethod
    def _open_dropdown(parent, dropdown_label: str) -> bool:
        dropdown = XingtuBrowserCollector._find_dropdown_in_line(parent, dropdown_label)
        dropdown.scroll_into_view_if_needed(timeout=3000)
        for trigger_sel in (
            ".el-dropdown-selfdefine",
            ".refer-label",
            ".star-score-button",
            ".base-market-dropdown-button",
        ):
            trigger = dropdown.locator(trigger_sel).first
            try:
                if trigger.is_visible(timeout=800):
                    trigger.click()
                    return True
            except Exception:
                continue
        dropdown.click()
        return True

    @staticmethod
    def _click_dropdown_filter(
        page,
        parent_line: str,
        dropdown_label: str,
        option: str,
        section: str | None = None,
    ) -> bool:
        if not option or option == "不限":
            return False
        try:
            section_loc = XingtuBrowserCollector._filter_section_locator(page, section)
            parent = section_loc.locator(".market-filter-wrapper--line").filter(has_text=parent_line).first
            parent.scroll_into_view_if_needed(timeout=3000)
            XingtuBrowserCollector._open_dropdown(parent, dropdown_label)
            page.wait_for_timeout(500)

            menu = page.locator(".el-dropdown-menu:visible").last
            item = menu.get_by_text(option, exact=True).first
            if not item.is_visible(timeout=1500):
                item = page.get_by_text(option, exact=True).last
            item.click()
            logger.info("Clicked dropdown filter %s=%s", dropdown_label, option)
            return True
        except Exception:
            logger.debug(
                "Dropdown filter click failed: %s/%s=%s",
                parent_line,
                dropdown_label,
                option,
                exc_info=True,
            )
        return False

    @staticmethod
    def _fans_panel_section(option: str) -> str:
        if "占比大于" in option:
            return "粉丝性别"
        return "粉丝年龄"

    @staticmethod
    def _click_fans_panel_option(page, option: str) -> bool:
        panel = page.locator("div.panel").filter(has_text="粉丝年龄").first
        section = XingtuBrowserCollector._fans_panel_section(option)
        block = panel.locator("div.panel-content").filter(has_text=section).first
        block.locator("input.el-input__inner").first.click()
        page.wait_for_timeout(500)
        item = block.locator("li.el-select-dropdown__item").filter(has_text=option).first
        if not item.is_visible(timeout=1200):
            item = page.locator("div.el-select-dropdown:visible li.el-select-dropdown__item").filter(
                has_text=option
            ).first
        item.click()
        page.wait_for_timeout(300)
        return True

    @staticmethod
    def _click_fans_panel_options(page, options: list[str], section: str | None = "匹配度") -> bool:
        if not options:
            return False
        try:
            section_loc = XingtuBrowserCollector._filter_section_locator(page, section)
            parent = section_loc.locator(".market-filter-wrapper--line").filter(has_text="受众画像").first
            parent.scroll_into_view_if_needed(timeout=3000)
            XingtuBrowserCollector._open_dropdown(parent, "粉丝画像")
            page.wait_for_timeout(900)

            for option in options:
                XingtuBrowserCollector._click_fans_panel_option(page, option)

            panel = page.locator("div.panel").filter(has_text="粉丝年龄").first
            panel.get_by_text("确定", exact=True).click()
            page.wait_for_timeout(400)
            logger.info("Clicked fans panel options: %s", ", ".join(options))
            return True
        except Exception:
            logger.debug("Fans panel options click failed: %s", options, exc_info=True)
        return False

    @staticmethod
    def _click_fans_panel_filter(
        page,
        parent_line: str,
        dropdown_label: str,
        option: str,
        section: str | None = None,
    ) -> bool:
        return XingtuBrowserCollector._click_fans_panel_options(page, [option], section)

    @staticmethod
    def _click_quote_duration(page, option: str) -> bool:
        """性价比区块的合作数据 -> 达人报价"""
        if not option or option == "不限":
            return False
        try:
            section_loc = XingtuBrowserCollector._filter_section_locator(page, "性价比")
            line = section_loc.locator(".market-filter-wrapper--line").filter(has_text="合作数据").first
            line.scroll_into_view_if_needed(timeout=3000)
            trigger = line.get_by_text("达人报价", exact=False).first
            trigger.click()
            page.wait_for_timeout(600)
            for exact in (True, False):
                tag = page.get_by_text(option, exact=exact).last
                if tag.is_visible(timeout=1200):
                    tag.click()
                    logger.info("Clicked quote_duration=%s", option)
                    return True
        except Exception:
            logger.debug("Quote duration click failed: %s", option, exc_info=True)

        return XingtuBrowserCollector._click_inline_filter(page, "合作数据", option, "性价比")

    @staticmethod
    def _confirm_filter_panel(page) -> None:
        """粉丝画像等弹层确认，不点击「全选」避免覆盖已选条件"""
        for text in ("确定", "确认"):
            try:
                el = page.get_by_text(text, exact=True).last
                if el.is_visible(timeout=800):
                    el.click()
                    page.wait_for_timeout(400)
                    return
            except Exception:
                continue
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass

    @staticmethod
    def _click_theme_tag(page, label: str) -> bool:
        if not label:
            return False
        try:
            section_loc = XingtuBrowserCollector._filter_section_locator(page, "主题推荐")
            line = section_loc.locator(".market-filter-wrapper--line").first
            line.scroll_into_view_if_needed(timeout=3000)
            page.wait_for_timeout(300)
            tag = line.get_by_text(label, exact=True).first
            if tag.is_visible(timeout=1500):
                tag.click()
                logger.info("Clicked theme tag=%s", label)
                return True
        except Exception:
            logger.debug("Theme tag click failed: %s", label, exc_info=True)
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
                            const match = href.match(/author-homepage\\/(?:douyin-video|abstract|live|short-video)\\/(\\d{11,20})/i)
                                || href.match(/(\\d{11,20})/);
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
        skip_local_filters: bool = False,
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
            if skip_local_filters or passes_search_filters(raw, filters):
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
        profile_url = resolve_collected_profile_url(
            "douyin", platform_uid, profile_url, extra_data={"parsed": parsed, "xingtu_raw": xingtu_raw}
        )
        if profile_url and not parsed.get("profile_url"):
            parsed["profile_url"] = profile_url
            if not parsed.get("xingtu_homepage"):
                parsed["xingtu_homepage"] = profile_url
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
