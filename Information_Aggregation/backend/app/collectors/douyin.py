import logging
import random

from app.collectors.base import BaseCollector, RawInfluencer, SearchFilters
from app.collectors.filter_utils import passes_search_filters
from app.config import settings

logger = logging.getLogger(__name__)

_DOUYIN_NICKNAME_TEMPLATES = [
    "{keyword}达人{suffix}",
    "{keyword}小{suffix}",
    "爱{keyword}的{suffix}",
    "{suffix}吃播记",
]


class DouyinCollector(BaseCollector):
    platform = "douyin"

    def search(self, keyword: str, filters: SearchFilters) -> list[RawInfluencer]:
        mode = settings.COLLECTOR_MODE

        if mode == "browser":
            return self._search_via_xingtu_browser(keyword, filters)

        if mode == "api" and settings.DOUYIN_API_TOKEN:
            return self._search_via_api(keyword, filters)

        if mode == "mock" or settings.PLAYWRIGHT_FALLBACK_MOCK:
            return self._search_mock(keyword, filters)

        raise RuntimeError(f"未知采集模式: {mode}，请在 .env 设置 COLLECTOR_MODE=browser")

    def _search_via_xingtu_browser(self, keyword: str, filters: SearchFilters) -> list[RawInfluencer]:
        from app.collectors.xingtu_browser import XingtuBrowserCollector

        try:
            return XingtuBrowserCollector().search(keyword, filters)
        except Exception as exc:
            logger.exception("Xingtu Playwright collect failed")
            if settings.PLAYWRIGHT_FALLBACK_MOCK:
                logger.warning("Fallback to mock mode")
                return self._search_mock(keyword, filters)
            raise RuntimeError(f"星图 Playwright 采集失败: {exc}") from exc

    def _search_via_api(self, keyword: str, filters: SearchFilters) -> list[RawInfluencer]:
        import httpx

        logger.info("Douyin API collect: keyword=%s", keyword)
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(
                    f"{settings.DOUYIN_API_BASE}/star/author/search",
                    params={"keyword": keyword, "limit": filters.limit},
                    headers={"Authorization": f"Bearer {settings.DOUYIN_API_TOKEN}"},
                )
                if resp.status_code == 200:
                    return self._parse_api_response(keyword, resp.json(), filters)
        except Exception as exc:
            logger.warning("Douyin API failed: %s", exc)
        if settings.PLAYWRIGHT_FALLBACK_MOCK:
            return self._search_mock(keyword, filters)
        raise RuntimeError("星图 API 采集失败，请检查 DOUYIN_API_TOKEN")

    def _parse_api_response(
        self, keyword: str, data: dict, filters: SearchFilters
    ) -> list[RawInfluencer]:
        from app.utils.keyword_match import calc_keyword_match_score
        from app.collectors.xingtu_browser import _pick, _to_int

        items = data.get("data", {}).get("list", [])
        results: list[RawInfluencer] = []
        for item in items:
            nickname = str(_pick(item, ("nickname", "nick_name", "author_name")) or "")
            tags = item.get("tags") or []
            raw = RawInfluencer(
                platform="douyin",
                platform_uid=str(_pick(item, ("author_id", "star_id", "uid")) or ""),
                nickname=nickname,
                avatar_url=_pick(item, ("avatar", "avatar_uri", "avatar_url")),
                profile_url=item.get("homepage"),
                follower_count=_to_int(_pick(item, ("follower_count", "fans_num"))),
                engagement_rate=item.get("engagement_rate"),
                avg_views=_to_int(_pick(item, ("avg_play_count", "avg_play"))),
                source="xingtu",
                matched_tags=tags,
                match_score=calc_keyword_match_score(keyword, nickname, tags),
                extra_data={
                    "recent_gmv": item.get("gmv_30d"),
                    "showcase_count": item.get("showcase_count"),
                    "quote_range": item.get("quote_range"),
                },
            )
            if passes_search_filters(raw, filters):
                results.append(raw)
        return results[: filters.limit]

    def _search_mock(self, keyword: str, filters: SearchFilters) -> list[RawInfluencer]:
        import hashlib

        logger.info("Douyin mock collect: keyword=%s", keyword)
        count = min(filters.limit, random.randint(8, 15))
        suffixes = ["阿明", "小红", "大胃王", "探店", "美食家", "小厨", "吃货", "记录"]
        results: list[RawInfluencer] = []

        for i in range(count):
            suffix = random.choice(suffixes)
            template = random.choice(_DOUYIN_NICKNAME_TEMPLATES)
            nickname = template.format(keyword=keyword, suffix=suffix)
            platform_uid = hashlib.md5(f"{keyword}-{nickname}-{i}".encode()).hexdigest()[:16]
            follower_count = random.randint(10000, 2000000)
            tags = [keyword, random.choice(["美食", "生活", "探店", "vlog"])]

            raw = RawInfluencer(
                platform="douyin",
                platform_uid=platform_uid,
                nickname=nickname,
                follower_count=follower_count,
                avg_views=int(follower_count * random.uniform(0.02, 0.15)),
                engagement_rate=round(random.uniform(0.02, 0.08), 4),
                source="xingtu_mock",
                matched_tags=tags,
                match_score=round(random.uniform(60, 95), 2),
                extra_data={"content_type": keyword, "mock": True},
            )
            if passes_search_filters(raw, filters):
                results.append(raw)

        results.sort(key=lambda x: x.match_score, reverse=True)
        return results
