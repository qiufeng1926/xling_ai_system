"""从蒲公英 API/DOM 数据中解析小红书达人字段"""

from __future__ import annotations

import re
from typing import Any

from app.utils.xingtu_fields import (
    _collect_direct_urls,
    _deep_pick,
    _normalize_engagement_rate,
    _normalize_gender,
    _normalize_tag_list,
    _normalize_url,
)

KOL_ID_KEYS = ("userId", "user_id", "kol_id", "kolId", "blogger_id", "red_id", "redId")
NICKNAME_KEYS = ("nick_name", "nickname", "name", "user_name", "kol_name", "blogger_name")
FOLLOWER_KEYS = ("fans_count", "fan_count", "follower_count", "followers", "fans_num")
AVATAR_KEYS = ("avatar", "avatar_url", "head_photo", "image", "avatar_uri")
TAG_KEYS = ("tags", "tag_list", "content_tags", "note_tags", "categories")
RED_ID_KEYS = ("red_id", "redId", "xhs_id", "unique_id", "display_id")
ENGAGEMENT_KEYS = (
    "engagement_rate",
    "interact_rate",
    "interaction_rate",
    "note_interact_rate",
    "avg_interact_rate",
)
MCN_KEYS = ("mcn_name", "agency_name", "signed_mcn_name", "organization_name", "mcn")
NOTE_AVG_KEYS = ("avg_read", "avg_read_count", "note_read_avg", "avg_play", "avg_views")


def _is_valid_xhs_profile_url(url: str) -> bool:
    lower = url.lower()
    if "xiaohongshu.com/user/profile/" in lower:
        return True
    if "xiaohongshu.com/search_result" in lower:
        return False
    if "pgy.xiaohongshu.com" in lower and "kol" in lower:
        return True
    return False


def _pick_kol_id(source: dict) -> str | None:
    for key in KOL_ID_KEYS:
        val = source.get(key)
        if val is not None and str(val).strip():
            text = str(val).strip()
            if text.isdigit() and len(text) >= 8:
                return text
            if len(text) >= 6:
                return text

    for block_key in ("user", "kol", "blogger", "author", "kol_info"):
        block = source.get(block_key)
        if isinstance(block, dict):
            for key in KOL_ID_KEYS:
                val = block.get(key)
                if val is not None and str(val).strip():
                    return str(val).strip()
    return None


def build_xhs_profile_url(user_id: str | None) -> str | None:
    if not user_id:
        return None
    return f"https://www.xiaohongshu.com/user/profile/{user_id}"


def build_pugongying_kol_url(kol_id: str | None) -> str | None:
    if not kol_id:
        return None
    return f"https://pgy.xiaohongshu.com/solar/pre-trade/note/kol/{kol_id}"


def extract_mcn_name_from_item(item: dict) -> str | None:
    from app.utils.mcn_utils import normalize_mcn_name

    for key in MCN_KEYS:
        found = normalize_mcn_name(item.get(key))
        if found:
            return found
    nested = _deep_pick(item, MCN_KEYS)
    return normalize_mcn_name(nested)


def extract_profile_url(item: dict) -> str | None:
    urls = _collect_direct_urls(item)
    for url in urls:
        if _is_valid_xhs_profile_url(url):
            return url

    nested_url = _normalize_url(_deep_pick(item, ("homepage", "profile_url", "home_page", "user_url")))
    if nested_url and _is_valid_xhs_profile_url(nested_url):
        return nested_url

    kol_id = _pick_kol_id(item)
    return build_xhs_profile_url(kol_id)


def parse_pugongying_item(item: dict[str, Any]) -> dict[str, Any]:
    raw = item.get("pugongying_raw") if isinstance(item.get("pugongying_raw"), dict) else {}
    source = {**raw, **{k: v for k, v in item.items() if k != "pugongying_raw"}}

    kol_id = _pick_kol_id(source)
    red_id = _deep_pick(source, RED_ID_KEYS)
    mcn_name = extract_mcn_name_from_item(source)

    styles: list[str] = []
    for key in TAG_KEYS:
        styles.extend(_normalize_tag_list(source.get(key)))
    styles = list(dict.fromkeys(styles))[:15]

    engagement = _normalize_engagement_rate(_deep_pick(source, ENGAGEMENT_KEYS))
    profile_url = extract_profile_url(source)
    pgy_homepage = build_pugongying_kol_url(kol_id)

    avg_read = _deep_pick(source, NOTE_AVG_KEYS)
    try:
        avg_read_int = int(float(avg_read)) if avg_read not in (None, "") else None
    except (TypeError, ValueError):
        avg_read_int = None

    contact_phone = _deep_pick(source, ("phone", "contact_phone", "mobile"))
    contact_wechat = _deep_pick(source, ("wechat", "contact_wechat", "weixin"))

    return {
        "profile_url": profile_url,
        "xhs_homepage": profile_url,
        "pgy_homepage": pgy_homepage,
        "kol_id": kol_id,
        "short_id": str(red_id) if red_id else None,
        "mcn_name": mcn_name,
        "city": _deep_pick(source, ("city", "city_name", "location", "area")),
        "gender": _normalize_gender(_deep_pick(source, ("gender", "sex"))),
        "engagement_rate": engagement,
        "avg_views": avg_read_int,
        "content_styles": styles,
        "persona_traits": [],
        "contact": {
            "phone": str(contact_phone).strip() if contact_phone else None,
            "wechat": str(contact_wechat).strip() if contact_wechat else None,
        },
    }


def choose_best_profile_url(parsed: dict[str, Any], item: dict[str, Any]) -> str | None:
    merged = {**(item.get("pugongying_raw") or {}), **item}
    url = extract_profile_url(merged)
    if url:
        return url
    for key in ("xhs_homepage", "profile_url", "pgy_homepage"):
        candidate = parsed.get(key)
        if candidate and _is_valid_xhs_profile_url(str(candidate)):
            return str(candidate)
    return None


def parse_dom_text_fields(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    rate_match = re.search(r"互动率[：:\s]*([\d.]+)\s*%?", text)
    if rate_match:
        fields["interact_rate"] = rate_match.group(1)
    id_match = re.search(r"小红书号[：:\s]*([^\n\r\s]+)", text)
    if id_match:
        fields["red_id"] = id_match.group(1).strip()
    mcn_match = re.search(r"MCN[：:\s]+([^\n\r]+)", text, re.I)
    if mcn_match:
        fields["mcn_name"] = mcn_match.group(1).strip()
    return fields
