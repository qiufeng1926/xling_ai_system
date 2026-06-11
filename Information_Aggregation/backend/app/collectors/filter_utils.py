"""采集结果本地筛选（星图页面筛选 + 二次校验）"""

from app.collectors.base import RawInfluencer, SearchFilters
from app.constants.xingtu_filters import FOLLOWER_TIER_RANGES


def resolve_follower_bounds(filters: SearchFilters) -> tuple[int | None, int | None]:
    follower_min = filters.follower_min
    follower_max = filters.follower_max
    if filters.follower_tier and filters.follower_tier in FOLLOWER_TIER_RANGES:
        tier_min, tier_max = FOLLOWER_TIER_RANGES[filters.follower_tier]
        if tier_min is not None:
            follower_min = max(follower_min or 0, tier_min) or tier_min
        if tier_max is not None:
            follower_max = min(follower_max, tier_max) if follower_max else tier_max
    return follower_min, follower_max


def _pick_quote(raw: RawInfluencer) -> int | None:
    extra = raw.extra_data or {}
    for key in ("quote_min", "quote_max", "price_min", "price_max"):
        val = extra.get(key)
        if val is not None:
            try:
                return int(float(val))
            except (TypeError, ValueError):
                continue
    xingtu = extra.get("xingtu_raw") or {}
    for key in ("quote_min", "quote_max", "price_min", "price_max"):
        val = xingtu.get(key)
        if val is not None:
            try:
                return int(float(val))
            except (TypeError, ValueError):
                continue
    return None


def passes_search_filters(raw: RawInfluencer, filters: SearchFilters) -> bool:
    follower_min, follower_max = resolve_follower_bounds(filters)

    if follower_min and raw.follower_count < follower_min:
        return False
    if follower_max and raw.follower_count > follower_max:
        return False
    if filters.avg_views_min and (raw.avg_views or 0) < filters.avg_views_min:
        return False
    if filters.expected_play_min and (raw.avg_views or 0) < filters.expected_play_min:
        return False
    if filters.interaction_rate_min:
        rate = raw.engagement_rate or 0
        threshold = filters.interaction_rate_min
        if threshold > 1 and rate <= 1:
            threshold = threshold / 100
        if rate < threshold:
            return False

    quote = _pick_quote(raw)
    if filters.quote_min and quote is not None and quote < filters.quote_min:
        return False
    if filters.quote_max and quote is not None and quote > filters.quote_max:
        return False

    if filters.creator_gender:
        gender = (raw.extra_data or {}).get("xingtu_raw", {}).get("gender")
        gender_map = {"1": "男", "2": "女", "男": "男", "女": "女"}
        if gender and gender_map.get(str(gender)) != filters.creator_gender:
            return False

    return True
