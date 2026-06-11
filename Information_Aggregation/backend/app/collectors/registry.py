from app.collectors.base import BaseCollector
from app.collectors.douyin import DouyinCollector
from app.collectors.xiaohongshu import XiaohongshuCollector

_COLLECTORS: dict[str, BaseCollector] = {
    "douyin": DouyinCollector(),
    "xiaohongshu": XiaohongshuCollector(),
}


def get_collector(platform: str) -> BaseCollector:
    collector = _COLLECTORS.get(platform)
    if not collector:
        raise ValueError(f"暂不支持平台: {platform}")
    return collector


def supported_platforms() -> list[str]:
    return list(_COLLECTORS.keys())
