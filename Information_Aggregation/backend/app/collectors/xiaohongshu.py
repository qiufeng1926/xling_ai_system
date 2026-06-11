import logging
import random

from app.collectors.base import BaseCollector, RawInfluencer, SearchFilters
from app.collectors.filter_utils import passes_search_filters
from app.config import settings

logger = logging.getLogger(__name__)


class XiaohongshuCollector(BaseCollector):
    platform = "xiaohongshu"

    def search(self, keyword: str, filters: SearchFilters) -> list[RawInfluencer]:
        mode = settings.COLLECTOR_MODE

        if mode == "browser":
            return self._search_via_pugongying_browser(keyword, filters)

        if mode == "mock" or settings.PLAYWRIGHT_FALLBACK_MOCK:
            return self._search_mock(keyword, filters)

        raise RuntimeError("小红书采集请设置 COLLECTOR_MODE=browser，并配置蒲公英登录态")

    def _search_via_pugongying_browser(self, keyword: str, filters: SearchFilters) -> list[RawInfluencer]:
        from app.collectors.pugongying_browser import PugongyingBrowserCollector

        try:
            return PugongyingBrowserCollector().search(keyword, filters)
        except Exception as exc:
            logger.exception("Pugongying Playwright collect failed")
            if settings.PLAYWRIGHT_FALLBACK_MOCK:
                logger.warning("Fallback to mock mode")
                return self._search_mock(keyword, filters)
            raise RuntimeError(f"蒲公英 Playwright 采集失败: {exc}") from exc

    def _search_mock(self, keyword: str, filters: SearchFilters) -> list[RawInfluencer]:
        import hashlib

        logger.info("Xiaohongshu mock collect: keyword=%s", keyword)
        count = min(filters.limit, random.randint(8, 15))
        suffixes = ["小姐", "同学", "日记", "分享", "种草", "生活家"]
        results: list[RawInfluencer] = []

        for i in range(count):
            suffix = random.choice(suffixes)
            nickname = f"{keyword}{suffix}{i + 1}"
            platform_uid = hashlib.md5(f"{keyword}-{nickname}-{i}".encode()).hexdigest()[:16]
            follower_count = random.randint(5000, 800000)
            tags = [keyword, random.choice(["美妆", "穿搭", "探店", "护肤"])]

            raw = RawInfluencer(
                platform="xiaohongshu",
                platform_uid=platform_uid,
                nickname=nickname,
                follower_count=follower_count,
                avg_views=int(follower_count * random.uniform(0.05, 0.2)),
                engagement_rate=round(random.uniform(0.02, 0.12), 4),
                source="pugongying_mock",
                matched_tags=tags,
                match_score=round(random.uniform(60, 95), 2),
                extra_data={"content_type": keyword, "mock": True},
            )
            if passes_search_filters(raw, filters):
                results.append(raw)

        results.sort(key=lambda x: x.match_score, reverse=True)
        return results
