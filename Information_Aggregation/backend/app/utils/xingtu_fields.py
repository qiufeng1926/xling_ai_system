"""从星图 API/DOM 数据中解析达人字段"""

from __future__ import annotations

import re
from typing import Any

PROFILE_URL_KEYS = (
    "homepage",
    "profile_url",
    "home_page",
    "author_url",
    "dy_homepage",
    "web_homepage",
    "home_url",
    "author_homepage",
    "dy_homepage_url",
    "homepage_url",
    "user_homepage",
)
SEC_UID_KEYS = ("sec_uid", "sec_user_id", "sec_user_uid")
# 仅用于星图主页 URL，不用泛化的 id/uid（易误匹配标签、分类等嵌套 id）
STAR_ID_KEYS = ("star_id",)
AUTHOR_ID_FOR_URL_KEYS = ("star_id", "author_id")
UNIQUE_ID_KEYS = ("unique_id", "short_id", "aweme_id", "douyin_id", "display_id")
ENGAGEMENT_KEYS = (
    "engagement_rate",
    "interact_rate",
    "interaction_rate",
    "interact_ratio",
    "interaction_ratio",
    "avg_interact_rate",
    "interact_rate_avg",
    "expected_interact_rate",
)
PHONE_KEYS = ("contact_phone", "phone", "mobile", "tel", "phone_number", "contact_mobile")
WECHAT_KEYS = ("contact_wechat", "wechat", "weixin", "wx", "wechat_id")
CITY_KEYS = ("city", "city_name", "location", "region", "province_city", "area")
GENDER_KEYS = ("gender", "sex")
STYLE_KEYS = (
    "content_tags",
    "video_style",
    "content_style",
    "category_tags",
    "style_tags",
    "content_category",
    "label_list",
    "persona_tags",
    "tags",
    "tag_list",
)
PERSONA_KEYS = ("persona", "persona_traits", "character_tags", "creator_persona")
AVG_PLAY_KEYS = ("avg_play", "avg_play_count", "play_count_avg", "average_play", "expect_play")
EXPECTED_PLAY_KEYS = (
    "expect_play",
    "expect_play_count",
    "expected_play_count",
    "expected_play",
    "expect_play_num",
    "expected_views",
    "predict_play",
    "predict_play_count",
    "play_count_expect",
    "expect_vv",
    "expected_vv",
)
CREATOR_TYPE_KEYS = (
    "creator_type",
    "star_type",
    "author_type",
    "price_type",
    "cooperation_type",
    "task_type",
    "creator_category",
    "type_name",
    "star_price_type",
    "price_type_name",
    "cooperation_form_name",
)
COMPLETION_RATE_KEYS = (
    "completion_rate",
    "finish_rate",
    "complete_rate",
    "play_over_rate",
    "over_play_rate",
    "finish_play_rate",
    "video_finish_rate",
    "play_finish_rate",
    "finish_ratio",
)
DEAL_RATE_KEYS = (
    "deal_rate",
    "order_rate",
    "convert_rate",
    "conversion_rate",
    "transaction_rate",
    "cvr",
    "order_finish_rate",
    "trade_rate",
    "deal_ratio",
)


def _deep_pick(obj: Any, keys: tuple[str, ...], depth: int = 0) -> Any:
    if depth > 8:
        return None
    if isinstance(obj, dict):
        for key in keys:
            if key in obj and obj[key] not in (None, "", [], {}):
                return obj[key]
        for value in obj.values():
            found = _deep_pick(value, keys, depth + 1)
            if found not in (None, "", [], {}):
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _deep_pick(item, keys, depth + 1)
            if found not in (None, "", [], {}):
                return found
    return None


def _is_valid_sec_uid(value: str) -> bool:
    """抖音 sec_uid 通常为 MS 开头的 base64 风格字符串"""
    if not value or len(value) < 20:
        return False
    if value.isdigit():
        return False
    return bool(re.match(r"^[A-Za-z0-9_=-]+$", value))


def _is_valid_star_id(value: str) -> bool:
    """星图 star_id / author_id 为大整数，排除粉丝量等误匹配"""
    if not value or not str(value).isdigit():
        return False
    length = len(str(value))
    return 11 <= length <= 20


def _is_valid_profile_url(url: str) -> bool:
    lower = url.lower()
    if "douyin.com/search" in lower:
        return False
    if "douyin.com/user/" in lower:
        return True
    if "xingtu.cn" in lower and ("/creator/" in lower or "author-homepage" in lower):
        return True
    return False


def _pick_star_id(source: dict) -> str | None:
    """仅从明确字段取 star_id，避免 deep_pick 误取嵌套 id"""
    for key in AUTHOR_ID_FOR_URL_KEYS:
        val = source.get(key)
        if val is not None and _is_valid_star_id(str(val)):
            return str(val)

    author = source.get("author")
    if isinstance(author, dict):
        for key in AUTHOR_ID_FOR_URL_KEYS:
            val = author.get(key)
            if val is not None and _is_valid_star_id(str(val)):
                return str(val)

    star_info = source.get("star_info") or source.get("author_info")
    if isinstance(star_info, dict):
        for key in AUTHOR_ID_FOR_URL_KEYS:
            val = star_info.get(key)
            if val is not None and _is_valid_star_id(str(val)):
                return str(val)
    return None


def _pick_sec_uid(source: dict) -> str | None:
    for key in SEC_UID_KEYS:
        val = source.get(key)
        if val and _is_valid_sec_uid(str(val)):
            return str(val)

    for block_key in ("author", "star_info", "author_info", "user_info"):
        block = source.get(block_key)
        if isinstance(block, dict):
            for key in SEC_UID_KEYS:
                val = block.get(key)
                if val and _is_valid_sec_uid(str(val)):
                    return str(val)
    return None


def _collect_direct_urls(source: dict) -> list[str]:
    urls: list[str] = []

    def add(url: Any) -> None:
        normalized = _normalize_url(url)
        if normalized and _is_valid_profile_url(normalized) and normalized not in urls:
            urls.append(normalized)

    for key in PROFILE_URL_KEYS:
        add(source.get(key))

    for block_key in ("author", "star_info", "author_info"):
        block = source.get(block_key)
        if isinstance(block, dict):
            for key in PROFILE_URL_KEYS:
                add(block.get(key))

    nested = _deep_pick(source, PROFILE_URL_KEYS)
    add(nested)
    return urls


def _normalize_url(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, dict):
        for key in ("url", "link", "href", "homepage"):
            found = _normalize_url(value.get(key))
            if found:
                return found
        return None
    text = str(value).strip()
    if not text.startswith("http"):
        return None
    return text


def _normalize_count(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).replace(",", "").strip()
    multiplier = 1
    if "万" in text:
        multiplier = 10000
        text = text.replace("万", "")
    if re.search(r"[wW]", text):
        multiplier = 10000
        text = re.sub(r"[wW]", "", text)
    try:
        return int(float(text) * multiplier)
    except (TypeError, ValueError):
        return None


def _normalize_rate(value: Any) -> float | None:
    return _normalize_engagement_rate(value)


def _normalize_creator_type(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("name", "title", "label", "type_name", "value"):
            found = value.get(key)
            if found:
                return str(found).strip()
        return None
    text = str(value).strip()
    return text or None


def _normalize_engagement_rate(value: Any) -> float | None:
    if value is None or value == "":
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


def _normalize_gender(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in ("1", "男", "male", "M"):
        return "男"
    if text in ("2", "女", "female", "F"):
        return "女"
    return text or None


def _normalize_tag_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,，、/|]", value)
        return [p.strip() for p in parts if p.strip()]
    if isinstance(value, dict):
        name = value.get("name") or value.get("title") or value.get("label")
        return [str(name)] if name else []
    if isinstance(value, list):
        names: list[str] = []
        for item in value:
            names.extend(_normalize_tag_list(item))
        return names
    return [str(value)]


def _collect_styles(item: dict) -> list[str]:
    styles: list[str] = []
    seen: set[str] = set()
    for key in STYLE_KEYS:
        val = item.get(key)
        if val is None:
            continue
        for name in _normalize_tag_list(val):
            if name and name not in seen:
                seen.add(name)
                styles.append(name)
    nested = _deep_pick(item, STYLE_KEYS)
    if nested:
        for name in _normalize_tag_list(nested):
            if name and name not in seen:
                seen.add(name)
                styles.append(name)
    return styles[:15]


def _collect_persona(item: dict) -> list[str]:
    traits: list[str] = []
    for key in PERSONA_KEYS:
        val = item.get(key)
        if val:
            traits.extend(_normalize_tag_list(val))
    nested = _deep_pick(item, PERSONA_KEYS)
    if nested:
        traits.extend(_normalize_tag_list(nested))
    deduped: list[str] = []
    seen: set[str] = set()
    for t in traits:
        if t not in seen:
            seen.add(t)
            deduped.append(t)
    return deduped[:10]


def build_xingtu_homepage(star_id: str | None) -> str | None:
    if star_id and _is_valid_star_id(star_id):
        return f"https://www.xingtu.cn/ad/creator/author-homepage/douyin-video/{star_id}"
    return None


def build_douyin_homepage(sec_uid: str | None, unique_id: str | None = None) -> str | None:
    if sec_uid and _is_valid_sec_uid(sec_uid):
        return f"https://www.douyin.com/user/{sec_uid}"
    return None


def extract_profile_url(item: dict) -> str | None:
    direct_urls = _collect_direct_urls(item)
    if direct_urls:
        for url in direct_urls:
            if "douyin.com/user/" in url.lower():
                return url
        return direct_urls[0]

    sec_uid = _pick_sec_uid(item)
    if sec_uid:
        return build_douyin_homepage(sec_uid)

    star_id = _pick_star_id(item)
    return build_xingtu_homepage(star_id)


def choose_best_profile_url(parsed: dict[str, Any], item: dict[str, Any]) -> str | None:
    merged = {**(item.get("xingtu_raw") or {}), **item}
    url = extract_profile_url(merged)
    if url:
        return url

    for key in ("douyin_homepage", "xingtu_homepage", "profile_url"):
        candidate = parsed.get(key)
        if candidate and _is_valid_profile_url(str(candidate)):
            return str(candidate)
    return None


def extract_contact(item: dict) -> dict[str, str | None]:
    phone = _deep_pick(item, PHONE_KEYS)
    wechat = _deep_pick(item, WECHAT_KEYS)
    contact_block = item.get("contact") or item.get("contact_info") or item.get("contact_way")
    if isinstance(contact_block, dict):
        phone = phone or contact_block.get("phone") or contact_block.get("mobile")
        wechat = wechat or contact_block.get("wechat") or contact_block.get("weixin")
    return {
        "phone": str(phone).strip() if phone else None,
        "wechat": str(wechat).strip() if wechat else None,
    }


def parse_xingtu_item(item: dict[str, Any]) -> dict[str, Any]:
    """将星图原始 item 解析为结构化 parsed 字段"""
    xingtu_raw = item.get("xingtu_raw") if isinstance(item.get("xingtu_raw"), dict) else {}
    source = {**xingtu_raw, **{k: v for k, v in item.items() if k != "xingtu_raw"}}

    star_id = _pick_star_id(source)
    sec_uid = _pick_sec_uid(source)
    unique_id = _deep_pick(source, UNIQUE_ID_KEYS)
    contact = extract_contact(source)
    content_styles = _collect_styles(source)
    persona_traits = _collect_persona(source)

    engagement = _normalize_engagement_rate(_deep_pick(source, ENGAGEMENT_KEYS))
    xingtu_homepage = build_xingtu_homepage(star_id)
    douyin_homepage = build_douyin_homepage(sec_uid)
    profile_url = extract_profile_url(source) or douyin_homepage or xingtu_homepage

    avg_play = _deep_pick(source, EXPECTED_PLAY_KEYS) or _deep_pick(source, AVG_PLAY_KEYS)
    avg_play_int = _normalize_count(avg_play)
    expected_play = _normalize_count(_deep_pick(source, EXPECTED_PLAY_KEYS))
    if expected_play is None and avg_play_int is not None:
        expected_play = avg_play_int

    creator_type = _normalize_creator_type(_deep_pick(source, CREATOR_TYPE_KEYS))
    completion_rate = _normalize_rate(_deep_pick(source, COMPLETION_RATE_KEYS))
    deal_rate = _normalize_rate(_deep_pick(source, DEAL_RATE_KEYS))

    return {
        "profile_url": profile_url,
        "xingtu_homepage": xingtu_homepage,
        "douyin_homepage": douyin_homepage,
        "sec_uid": sec_uid,
        "short_id": str(unique_id) if unique_id else None,
        "star_id": star_id,
        "city": _deep_pick(source, CITY_KEYS),
        "gender": _normalize_gender(_deep_pick(source, GENDER_KEYS)),
        "engagement_rate": engagement,
        "avg_views": avg_play_int,
        "expected_play_count": expected_play,
        "creator_type": creator_type,
        "completion_rate": completion_rate,
        "deal_rate": deal_rate,
        "contact": contact,
        "content_styles": content_styles,
        "persona_traits": persona_traits,
    }


def merge_author_items(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """合并同一达人的多次 API 响应，保留更完整字段"""
    merged = dict(base)
    for key, value in incoming.items():
        if key.startswith("_"):
            continue
        if value in (None, "", [], {}):
            continue
        if key not in merged or merged[key] in (None, "", [], {}):
            merged[key] = value
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **{k: v for k, v in value.items() if v not in (None, "", [], {})}}
        elif isinstance(value, list) and isinstance(merged.get(key), list):
            combined = list(merged[key])
            for entry in value:
                if entry not in combined:
                    combined.append(entry)
            merged[key] = combined
    return merged


def needs_detail_enrichment(parsed: dict[str, Any]) -> bool:
    profile = parsed.get("profile_url")
    if not profile or not _is_valid_profile_url(str(profile)):
        return True
    if parsed.get("engagement_rate") is None:
        return True
    contact = parsed.get("contact") or {}
    if not contact.get("phone") and not contact.get("wechat"):
        return True
    if not parsed.get("content_styles"):
        return True
    return False


def build_profile_update_from_extra(extra_data: dict | None):
    """从采集 extra_data 生成 InfluencerProfile 更新内容"""
    if not extra_data:
        return None

    parsed = extra_data.get("parsed") or parse_xingtu_item(extra_data)
    contact = parsed.get("contact") or {}
    phone = contact.get("phone")
    wechat = contact.get("wechat")
    styles = parsed.get("content_styles") or []
    persona = parsed.get("persona_traits") or []

    contact_info = {k: v for k, v in {"phone": phone, "wechat": wechat}.items() if v}
    if not contact_info and not styles and not persona:
        return None

    from app.schemas import InfluencerProfileOut

    return InfluencerProfileOut(
        contact_info=contact_info or None,
        shooting_style=styles or None,
        persona_traits=persona or None,
    )


def merge_profile_patch(existing, patch) -> Any:
    """合并已有档案与采集补丁，保留已有非空字段"""
    from app.schemas import InfluencerProfileOut

    if patch is None:
        return None
    if existing is None:
        return patch

    base = InfluencerProfileOut.model_validate(existing)
    patch_data = patch.model_dump(exclude_unset=True)

    contact = dict(base.contact_info or {})
    for key, value in (patch_data.get("contact_info") or {}).items():
        if value and not contact.get(key):
            contact[key] = value

    styles = list(base.shooting_style or [])
    for style in patch_data.get("shooting_style") or []:
        if style and style not in styles:
            styles.append(style)

    persona = list(base.persona_traits or [])
    for trait in patch_data.get("persona_traits") or []:
        if trait and trait not in persona:
            persona.append(trait)

    policy = base.cooperation_policy or patch_data.get("cooperation_policy")
    notes = base.internal_notes or patch_data.get("internal_notes")

    return InfluencerProfileOut(
        contact_info=contact or None,
        shooting_style=styles or None,
        persona_traits=persona or None,
        cooperation_policy=policy,
        internal_notes=notes,
        last_contact_date=base.last_contact_date,
    )


def parse_dom_text_fields(text: str) -> dict[str, Any]:
    """从 DOM 卡片/表格文本补充字段"""
    fields: dict[str, Any] = {}

    rate_match = re.search(r"互动率[：:\s]*([\d.]+)\s*%?", text)
    if rate_match:
        fields["interact_rate"] = rate_match.group(1)

    completion_match = re.search(r"完播率[：:\s]*([\d.]+)\s*%?", text)
    if completion_match:
        fields["completion_rate"] = completion_match.group(1)

    deal_match = re.search(r"成交率[：:\s]*([\d.]+)\s*%?", text)
    if deal_match:
        fields["deal_rate"] = deal_match.group(1)

    expect_play_match = re.search(r"预期播放量[：:\s]*([\d,.]+[wW万]?)", text)
    if expect_play_match:
        fields["expect_play_count"] = expect_play_match.group(1)

    follower_match = re.search(r"粉丝数[：:\s]*([\d,.]+[wW万]?)", text)
    if follower_match:
        fields["follower_count"] = follower_match.group(1)

    creator_type_match = re.search(r"达人类型[：:\s]*([^\n\r]+)", text)
    if creator_type_match:
        fields["creator_type"] = creator_type_match.group(1).strip()

    city_match = re.search(r"(?:城市|地区)[：:\s]*([^\n\r]+)", text)
    if city_match:
        fields["city"] = city_match.group(1).strip()

    id_match = re.search(r"抖音号[：:\s]*([^\n\r\s]+)", text)
    if id_match:
        fields["unique_id"] = id_match.group(1).strip()

    gender_match = re.search(r"性别[：:\s]*([男女])", text)
    if gender_match:
        fields["gender"] = gender_match.group(1)

    phone_match = re.search(r"(?:电话|手机|联系方式)[：:\s]*([+\d\-]{6,})", text)
    if phone_match:
        fields["contact_phone"] = phone_match.group(1).strip()

    wechat_match = re.search(r"(?:微信|wechat)[：:\s]*([^\n\r\s]+)", text, re.I)
    if wechat_match:
        fields["contact_wechat"] = wechat_match.group(1).strip()

    style_match = re.search(r"(?:内容类型|视频风格|风格)[：:\s]*([^\n\r]+)", text)
    if style_match:
        fields["content_tags"] = style_match.group(1).strip()

    return fields
