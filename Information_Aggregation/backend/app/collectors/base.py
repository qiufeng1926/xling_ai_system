from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchFilters:
    # 合作诉求
    cooperation_purpose: str | None = None
    incentive_method: str | None = None
    cooperation_form: str | None = None
    creator_level: str | None = None
    # 达人配置
    creator_type: str | None = None
    follower_tier: str | None = None
    content_theme: str | None = None
    creator_gender: str | None = None
    follower_gender: str | None = None
    follower_age: str | None = None
    verified: str | None = None
    # 数据指标
    follower_min: int | None = None
    follower_max: int | None = None
    avg_views_min: int | None = None
    interaction_rate_min: float | None = None
    # 性价比
    quote_duration: str | None = None
    quote_min: int | None = None
    quote_max: int | None = None
    expected_play_min: int | None = None
    expected_cpm_max: float | None = None
    expected_cpe_max: float | None = None
    completion_rate_min: float | None = None
    # 主题推荐
    theme_tags: list[str] | None = None
    limit: int = 30

    @classmethod
    def from_dict(cls, data: dict | None) -> "SearchFilters":
        if not data:
            return cls()
        from dataclasses import fields

        known = {f.name for f in fields(cls)}
        kwargs: dict[str, Any] = {}
        for key, value in data.items():
            if key not in known or value in (None, "", []):
                continue
            kwargs[key] = value
        return cls(**kwargs)


@dataclass
class RawInfluencer:
    platform: str
    platform_uid: str
    nickname: str
    avatar_url: str | None = None
    profile_url: str | None = None
    follower_count: int = 0
    engagement_rate: float | None = None
    avg_views: int | None = None
    source: str = "auto_collect"
    matched_tags: list[str] = field(default_factory=list)
    match_score: float = 0.0
    extra_data: dict[str, Any] = field(default_factory=dict)


class BaseCollector(ABC):
    platform: str

    @abstractmethod
    def search(self, keyword: str, filters: SearchFilters) -> list[RawInfluencer]:
        pass