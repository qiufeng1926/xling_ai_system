"""预置标签种子数据"""

TAG_SEED: list[dict] = [
    # 内容类
    {"name": "美食", "category": "content", "level": 1},
    {"name": "美妆", "category": "content", "level": 1},
    {"name": "剧情", "category": "content", "level": 1},
    {"name": "穿搭", "category": "content", "level": 1},
    {"name": "探店", "category": "content", "level": 1},
    {"name": "吃播", "category": "content", "level": 1},
    {"name": "母婴", "category": "content", "level": 1},
    {"name": "游戏", "category": "content", "level": 1},
    {"name": "旅行", "category": "content", "level": 1},
    {"name": "汽车", "category": "content", "level": 1},
    {"name": "生活", "category": "content", "level": 1},
    {"name": "运动健身", "category": "content", "level": 1},
    {"name": "科技数码", "category": "content", "level": 1},
    {"name": "教育", "category": "content", "level": 1},
    {"name": "三农", "category": "content", "level": 1},
    # 风格类
    {"name": "口播", "category": "style", "level": 1},
    {"name": "Vlog", "category": "style", "level": 1},
    {"name": "剧情向", "category": "style", "level": 1},
    {"name": "测评", "category": "style", "level": 1},
    {"name": "教程", "category": "style", "level": 1},
    # 商业类
    {"name": "高转化", "category": "business", "level": 1},
    {"name": "种草型", "category": "business", "level": 1},
    {"name": "直播型", "category": "business", "level": 1},
    {"name": "品牌合作", "category": "business", "level": 1},
    # 来源类
    {"name": "星图采集", "category": "source", "level": 1},
    {"name": "人工录入", "category": "source", "level": 1},
    {"name": "Excel导入", "category": "source", "level": 1},
]

TAG_CATEGORY_LABELS: dict[str, str] = {
    "content": "内容类",
    "style": "风格类",
    "business": "商业类",
    "source": "来源类",
}
