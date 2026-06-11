"""蒲公英（小红书）筛选配置 — MVP 仅保留通用指标"""

from typing import Any

DEFAULT_OPTION = {"label": "不限", "value": ""}


def _opts(*labels: str) -> list[dict[str, str]]:
    return [DEFAULT_OPTION] + [{"label": lb, "value": lb} for lb in labels]


FILTER_GROUPS: list[dict[str, Any]] = [
    {
        "key": "creator",
        "label": "博主配置",
        "fields": [
            {
                "key": "content_theme",
                "label": "内容类目",
                "type": "single",
                "options": _opts(
                    "美妆", "护肤", "穿搭", "美食", "旅行", "母婴", "家居", "健身",
                    "数码", "教育", "职场", "探店", "Vlog", "剧情",
                ),
            },
            {
                "key": "creator_gender",
                "label": "博主性别",
                "type": "single",
                "options": _opts("男", "女"),
            },
        ],
    },
    {
        "key": "metrics",
        "label": "数据指标",
        "fields": [
            {
                "key": "follower_min",
                "label": "粉丝下限",
                "type": "number",
                "min": 0,
                "placeholder": "不限",
            },
            {
                "key": "follower_max",
                "label": "粉丝上限",
                "type": "number",
                "min": 0,
                "placeholder": "不限",
            },
            {
                "key": "interaction_rate_min",
                "label": "最低互动率",
                "type": "number",
                "min": 0,
                "max": 100,
                "step": 0.1,
                "unit": "%",
                "placeholder": "不限",
            },
        ],
    },
    {
        "key": "task",
        "label": "采集设置",
        "fields": [
            {
                "key": "limit",
                "label": "采集数量",
                "type": "number",
                "min": 1,
                "max": 200,
                "default": 30,
            },
        ],
    },
]


def get_filter_options() -> dict[str, Any]:
    return {"groups": FILTER_GROUPS, "platform": "xiaohongshu"}
