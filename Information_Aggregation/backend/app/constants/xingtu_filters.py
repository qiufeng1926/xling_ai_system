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
                "label": "合作目的",
                "type": "single",
                "options": _opts(
                    "种草", "品牌曝光", "短视频引流", "直播带货", "矩阵分发", "搜索增效",
                ),
            },
            {
                "key": "incentive_method",
                "label": "激励方式",
                "type": "single",
                "options": _opts("现金", "资源位", "流量券", "样品", "佣金"),
            },
            {
                "key": "cooperation_form",
                "label": "合作形式",
                "type": "single",
                "options": _opts("视频", "直播"),
            },
            {
                "key": "creator_level",
                "label": "达人等级",
                "type": "single",
                "options": _opts("头部", "肩部", "腰部", "尾部"),
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
                    "美妆", "剧情", "穿搭", "游戏", "二次元", "旅行", "萌宠", "生活",
                    "娱乐", "搞笑", "美食", "情感", "运动健身", "科技数码", "教育",
                    "职场", "汽车", "母婴", "艺术文化", "财经", "三农", "摄影", "音乐",
                    "舞蹈", "户外", "影视", "集体号",
                ),
            },
            {
                "key": "follower_tier",
                "label": "粉丝量级",
                "type": "single",
                "options": _opts("1w-10w", "10w-50w", "50w-100w", "100w-500w", "500w+"),
            },
            {
                "key": "content_theme",
                "label": "内容主题",
                "type": "single",
                "options": _opts(
                    "妆容造型", "身材管理", "亲子育儿", "美食教程与测评", "居家生活",
                    "手机/电脑/数码分享", "剧情演绎", "职场干货", "旅行攻略", "运动健身",
                    "穿搭指南", "探店打卡", "Vlog日常",
                ),
            },
            {
                "key": "creator_gender",
                "label": "达人性别",
                "type": "single",
                "options": _opts("男", "女"),
            },
            {
                "key": "follower_gender",
                "label": "粉丝性别",
                "type": "single",
                "options": _opts("男", "女"),
            },
            {
                "key": "follower_age",
                "label": "粉丝年龄",
                "type": "single",
                "options": _opts("18-23", "24-30", "31-40", "41-50", "50+"),
            },
            {
                "key": "verified",
                "label": "实名认证",
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
                    {"label": "星图优选达人", "value": "星图优选达人"},
                    {"label": "抖音精选计划达人", "value": "抖音精选计划达人"},
                    {"label": "大牌同款达人", "value": "大牌同款达人"},
                    {"label": "新锐达人", "value": "新锐达人"},
                    {"label": "优质潜力达人", "value": "优质潜力达人"},
                    {"label": "品牌首选达人", "value": "品牌首选达人"},
                    {"label": "行业高潜品牌潜力达人", "value": "行业高潜品牌潜力达人"},
                    {"label": "活动达人", "value": "活动达人"},
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

# 粉丝量级 -> 数值区间（用于本地二次筛选）
FOLLOWER_TIER_RANGES: dict[str, tuple[int | None, int | None]] = {
    "1w-10w": (10_000, 100_000),
    "10w-50w": (100_000, 500_000),
    "50w-100w": (500_000, 1_000_000),
    "100w-500w": (1_000_000, 5_000_000),
    "500w+": (5_000_000, None),
}

# Playwright 页面上可点击的筛选项：字段 key -> 星图页面上的行标题
PAGE_FILTER_LABELS: dict[str, str] = {
    "cooperation_purpose": "合作目的",
    "incentive_method": "激励方式",
    "cooperation_form": "合作形式",
    "creator_level": "达人等级",
    "creator_type": "达人类型",
    "follower_tier": "粉丝量级",
    "content_theme": "内容主题",
    "creator_gender": "达人性别",
    "follower_gender": "粉丝性别",
    "follower_age": "粉丝年龄",
    "verified": "实名认证",
    "quote_duration": "合作报价",
}


def get_filter_options() -> dict[str, Any]:
    return {"groups": FILTER_GROUPS}
