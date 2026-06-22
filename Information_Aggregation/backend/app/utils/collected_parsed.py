"""解析采集结果 extra_data（按平台）"""

from app.utils.pugongying_fields import parse_pugongying_item, _is_valid_xhs_profile_url
from app.utils.xingtu_fields import parse_xingtu_item, _is_valid_profile_url as _is_valid_douyin_profile_url


def parse_collected_parsed(extra_data: dict | None, platform: str) -> dict:
    if not extra_data:
        return {}
    if extra_data.get("parsed"):
        return extra_data["parsed"]
    if platform == "xiaohongshu":
        return parse_pugongying_item(extra_data)
    return parse_xingtu_item(extra_data)


def build_profile_update_from_extra(extra_data: dict | None, platform: str = "douyin"):
    from app.schemas import InfluencerProfileOut

    if not extra_data:
        return None

    parsed = parse_collected_parsed(extra_data, platform)
    contact = parsed.get("contact") or {}
    phone = contact.get("phone")
    wechat = contact.get("wechat")
    styles = parsed.get("content_styles") or []
    persona = parsed.get("persona_traits") or []

    contact_info = {k: v for k, v in {"phone": phone, "wechat": wechat}.items() if v}
    if not contact_info and not styles and not persona:
        return None

    return InfluencerProfileOut(
        contact_info=contact_info or None,
        shooting_style=styles or None,
        persona_traits=persona or None,
    )


def is_valid_profile_url(url: str | None, platform: str) -> bool:
    if not url:
        return False
    if platform == "xiaohongshu":
        return _is_valid_xhs_profile_url(url)
    return _is_valid_douyin_profile_url(url)


def resolve_collected_profile_url(
    platform: str,
    platform_uid: str,
    profile_url: str | None = None,
    extra_data: dict | None = None,
) -> str | None:
    """从采集结果解析主页链接，必要时用 platform_uid 拼装"""
    if profile_url and is_valid_profile_url(profile_url, platform):
        return profile_url

    parsed = parse_collected_parsed(extra_data, platform) if extra_data else {}
    for key in ("profile_url", "douyin_homepage", "xingtu_homepage", "pgy_homepage"):
        candidate = parsed.get(key)
        if candidate and is_valid_profile_url(str(candidate), platform):
            return str(candidate)

    if platform == "douyin" and platform_uid:
        from app.utils.xingtu_fields import build_xingtu_homepage, _is_valid_star_id

        if _is_valid_star_id(str(platform_uid)):
            return build_xingtu_homepage(str(platform_uid))

    if platform == "xiaohongshu" and platform_uid:
        from app.utils.pugongying_fields import build_pugongying_kol_url, build_xhs_profile_url

        return build_xhs_profile_url(platform_uid) or build_pugongying_kol_url(platform_uid)

    return profile_url or None
