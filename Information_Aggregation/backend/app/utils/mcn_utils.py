"""从星图采集数据中解析 MCN/机构名称"""

from typing import Any

MCN_NAME_KEYS = (
    "mcn_name",
    "mcn_title",
    "mcn",
    "agency_name",
    "institution_name",
    "signed_mcn_name",
    "organization_name",
    "mcn_company_name",
    "broker_name",
    "mcn_info",
    "sign_mcn_name",
)

INVALID_MCN_NAMES = frozenset(
    {
        "",
        "-",
        "无",
        "暂无",
        "无mcn",
        "无mcn机构",
        "未签约",
        "未签约mcn",
        "个人",
        "个人达人",
        "未绑定",
        "null",
        "none",
    }
)


def normalize_mcn_name(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("name", "title", "mcn_name", "agency_name"):
            nested = normalize_mcn_name(value.get(key))
            if nested:
                return nested
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower().replace(" ", "")
    if lowered in INVALID_MCN_NAMES:
        return None
    if lowered.startswith("无") and len(text) <= 6:
        return None
    return text


def extract_mcn_name(data: dict | None) -> str | None:
    """从星图原始字段或 extra_data 中提取 MCN 名称"""
    if not data:
        return None

    direct = normalize_mcn_name(data.get("mcn_name"))
    if direct:
        return direct

    for key in MCN_NAME_KEYS:
        found = normalize_mcn_name(data.get(key))
        if found:
            return found

    xingtu_raw = data.get("xingtu_raw")
    if isinstance(xingtu_raw, dict):
        found = _search_mcn_in_object(xingtu_raw)
        if found:
            return found

    pugongying_raw = data.get("pugongying_raw")
    if isinstance(pugongying_raw, dict):
        found = _search_mcn_in_object(pugongying_raw)
        if found:
            return found

    return _search_mcn_in_object(data)


def _search_mcn_in_object(obj: Any, depth: int = 0) -> str | None:
    if depth > 6:
        return None
    if isinstance(obj, dict):
        for key in MCN_NAME_KEYS:
            if key in obj:
                found = normalize_mcn_name(obj[key])
                if found:
                    return found
        for value in obj.values():
            found = _search_mcn_in_object(value, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _search_mcn_in_object(item, depth + 1)
            if found:
                return found
    return None
