"""星图达人广场筛选指标配置（与巨量星图 UI 对齐，默认「不限」）"""

from typing import Any, Literal

FilterType = Literal["single", "multi", "number", "range"]

DEFAULT_OPTION = {"label": "不限", "value": ""}


def _opts(*labels: str) -> list[dict[str, str]]:
    return [DEFAULT_OPTION] + [{"label": lb, "value": lb} for lb in labels]


FILTER_GROUPS: list[dict[str, Any]] = [
    {
        "key": "cooperation",
        "label": "合作诉求",
        "fields": [
            {
                "key": "cooperation_purpose",
                "label": "营销目标",
                "type": "single",
                "options": _opts("品牌曝光", "破圈种草", "行动转化"),
            },
            {
                "key": "cooperation_form",
                "label": "题材类型",
                "type": "single",
                "options": _opts("短视频达人", "短剧演员", "短直达人", "其它题材"),
            },
        ],
    },
    {
        "key": "creator",
        "label": "达人配置",
        "fields": [
            {
                "key": "creator_type",
                "label": "达人类型",
                "type": "single",
                "options": _opts(
                    "美妆", "时尚", "萌宠", "测评", "游戏", "二次元", "旅行", "汽车", "生活",
                    "音乐", "舞蹈", "美食", "母婴亲子", "运动健身", "科技数码", "教育培训",
                    "颜值达人", "生活家居", "才艺技能", "影视娱乐", "艺术文化", "财经投资",
                    "三农", "剧情搞笑", "情感",
                ),
            },
            {
                "key": "follower_tier",
                "label": "粉丝数量",
                "type": "single",
                "options": _opts(
                    "10w以下", "10w-100w", "100w-300w", "300w-500w", "500w-1000w", "1000w以上",
                ),
            },
            {
                "key": "content_theme",
                "label": "内容主题",
                "type": "single",
                "options": _opts(
                    "妆容妆造", "穿搭指南", "亲子育儿", "美食教程与测评", "精彩车生活",
                    "手机/数码/家电分享", "剧情演绎", "萌宠养护", "旅行攻略", "家居好物", "运动户外",
                ),
            },
            {
                "key": "creator_gender",
                "label": "达人性别",
                "type": "single",
                "options": _opts("男性", "女性"),
            },
            {
                "key": "follower_gender",
                "label": "粉丝性别",
                "type": "single",
                "options": _opts(
                    "男性占比大于50%", "男性占比大于60%", "女性占比大于50%", "女性占比大于60%",
                ),
            },
            {
                "key": "follower_age",
                "label": "粉丝年龄",
                "type": "single",
                "options": _opts(
                    "18-23岁居多", "24-30岁居多", "31-40岁居多", "41-50岁居多", "大于50岁居多",
                ),
            },
            {
                "key": "verified",
                "label": "黄v认证",
                "type": "single",
                "options": _opts("已认证", "未认证"),
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
                "placeholder": "不限",
                "unit": "人",
            },
            {
                "key": "follower_max",
                "label": "粉丝上限",
                "type": "number",
                "placeholder": "不限",
                "unit": "人",
            },
            {
                "key": "avg_views_min",
                "label": "播放量下限",
                "type": "number",
                "placeholder": "不限",
                "unit": "次",
            },
            {
                "key": "interaction_rate_min",
                "label": "互动率下限",
                "type": "number",
                "placeholder": "不限",
                "unit": "%",
                "step": 0.1,
            },
        ],
    },
    {
        "key": "cost",
        "label": "性价比",
        "fields": [
            {
                "key": "quote_duration",
                "label": "合作报价",
                "type": "single",
                "options": _opts("1-20s", "21-60s", "60s+"),
            },
            {
                "key": "quote_min",
                "label": "报价下限",
                "type": "number",
                "placeholder": "不限",
                "unit": "元",
            },
            {
                "key": "quote_max",
                "label": "报价上限",
                "type": "number",
                "placeholder": "不限",
                "unit": "元",
            },
            {
                "key": "expected_play_min",
                "label": "预期播放量",
                "type": "number",
                "placeholder": "不限",
                "unit": "次",
            },
            {
                "key": "expected_cpm_max",
                "label": "预期CPM上限",
                "type": "number",
                "placeholder": "不限",
                "unit": "元",
            },
            {
                "key": "expected_cpe_max",
                "label": "预期CPE上限",
                "type": "number",
                "placeholder": "不限",
                "unit": "元",
            },
            {
                "key": "completion_rate_min",
                "label": "完播率下限",
                "type": "number",
                "placeholder": "不限",
                "unit": "%",
                "step": 0.1,
            },
        ],
    },
    {
        "key": "theme",
        "label": "主题推荐",
        "fields": [
            {
                "key": "theme_tags",
                "label": "优选标签",
                "type": "multi",
                "options": [
                    {"label": "优选达人", "value": "优选达人"},
                    {"label": "抖音精选计划达人", "value": "抖音精选计划达人"},
                    {"label": "近期降价达人", "value": "近期降价达人"},
                    {"label": "新面孔达人", "value": "新面孔达人"},
                    {"label": "活动精选", "value": "活动精选"},
                    {"label": "种草优势达人", "value": "种草优势达人"},
                    {"label": "高性价比达人", "value": "高性价比达人"},
                    {"label": "带货优势达人", "value": "带货优势达人"},
                ],
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
                "placeholder": "30",
                "min": 1,
                "max": 200,
                "default": 30,
            },
        ],
    },
]

# 粉丝数量档位 -> 数值区间（用于本地二次筛选）
FOLLOWER_TIER_RANGES: dict[str, tuple[int | None, int | None]] = {
    "10w以下": (None, 100_000),
    "10w-100w": (100_000, 1_000_000),
    "100w-300w": (1_000_000, 3_000_000),
    "300w-500w": (3_000_000, 5_000_000),
    "500w-1000w": (5_000_000, 10_000_000),
    "1000w以上": (10_000_000, None),
    # 兼容旧任务配置
    "1w-10w": (10_000, 100_000),
    "10w-50w": (100_000, 500_000),
    "50w-100w": (500_000, 1_000_000),
    "100w-500w": (1_000_000, 5_000_000),
    "500w+": (5_000_000, None),
}

# Playwright 页面上可点击的筛选项：字段 key -> 星图页面上的行标题
PAGE_FILTER_LABELS: dict[str, str] = {
    "cooperation_purpose": "营销目标",
    "cooperation_form": "题材类型",
    "creator_type": "达人类型",
    "follower_tier": "粉丝数量",
    "content_theme": "内容主题",
    "creator_gender": "达人性别",
    "follower_gender": "粉丝性别",
    "follower_age": "粉丝年龄",
    "verified": "黄v认证",
    "quote_duration": "达人报价",
}

# 筛选项所属区块（用于滚动定位）
PAGE_FILTER_SECTIONS: dict[str, str] = {
    "cooperation_purpose": "合作诉求",
    "cooperation_form": "合作诉求",
    "creator_type": "匹配度",
    "follower_tier": "匹配度",
    "content_theme": "匹配度",
    "creator_gender": "匹配度",
    "follower_gender": "匹配度",
    "follower_age": "匹配度",
    "verified": "匹配度",
    "quote_duration": "性价比",
    "quote_min": "性价比",
    "quote_max": "性价比",
    "theme_tags": "主题推荐",
}

# 采集表单值 -> 星图页面上的展示文案（兼容旧任务）
PAGE_FILTER_VALUE_ALIASES: dict[str, dict[str, str]] = {
    "cooperation_purpose": {
        "种草": "破圈种草",
        "品牌曝光": "品牌曝光",
        "短视频引流": "行动转化",
        "直播带货": "行动转化",
        "矩阵分发": "行动转化",
        "搜索增效": "行动转化",
    },
    "cooperation_form": {
        "视频": "短视频达人",
        "直播": "短直达人",
    },
    "creator_gender": {"男": "男性", "女": "女性"},
    "follower_tier": {
        "1w-10w": "10w以下",
        "10w-50w": "10w-100w",
        "50w-100w": "10w-100w",
        "100w-500w": "100w-300w",
        "500w+": "500w-1000w",
    },
    "follower_gender": {
        "男": "男性占比大于50%",
        "女": "女性占比大于50%",
    },
    "follower_age": {
        "18-23": "18-23岁居多",
        "24-30": "24-30岁居多",
        "31-40": "31-40岁居多",
        "41-50": "41-50岁居多",
        "50+": "大于50岁居多",
    },
    "quote_duration": {
        "1-20s": "1-20s",
        "21-60s": "21-60s视频",
        "60s+": "60s以上",
    },
    "theme_tags": {
        "星图优选达人": "优选达人",
        "新锐达人": "新面孔达人",
        "大牌同款达人": "抖音精选品牌伙伴计划",
        "优质潜力达人": "高性价比达人",
        "品牌首选达人": "种草优势达人",
        "行业高潜品牌潜力达人": "带货优势达人",
        "活动达人": "活动精选",
    },
}

# Playwright 点击策略：inline=行内标签，dropdown=下拉，fans_panel=粉丝画像弹层
PAGE_FILTER_CLICK: dict[str, dict[str, Any]] = {
    "cooperation_purpose": {"type": "inline", "line": "营销目标", "section": "合作诉求"},
    "cooperation_form": {"type": "inline", "line": "题材类型", "section": "合作诉求"},
    "creator_type": {"type": "inline", "line": "达人类型", "section": "匹配度"},
    "content_theme": {"type": "inline", "line": "内容主题", "section": "匹配度"},
    "creator_gender": {
        "type": "dropdown",
        "parent_line": "背景信息",
        "dropdown": "达人性别",
        "section": "匹配度",
    },
    "follower_tier": {
        "type": "dropdown",
        "parent_line": "受众画像",
        "dropdown": "粉丝数量",
        "section": "匹配度",
    },
    "follower_gender": {
        "type": "fans_panel",
        "parent_line": "受众画像",
        "dropdown": "粉丝画像",
        "section": "匹配度",
    },
    "follower_age": {
        "type": "fans_panel",
        "parent_line": "受众画像",
        "dropdown": "粉丝画像",
        "section": "匹配度",
    },
    "verified": {
        "type": "dropdown",
        "parent_line": "背景信息",
        "dropdown": "黄v认证",
        "section": "匹配度",
    },
    "quote_duration": {"type": "quote", "section": "性价比"},
}


def get_filter_options() -> dict[str, Any]:
    return {"groups": FILTER_GROUPS}
