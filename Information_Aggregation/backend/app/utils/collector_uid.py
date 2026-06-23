"""采集阶段达人 UID 规范化，避免昵称当 ID 导致重复"""

from __future__ import annotations

from typing import Any

from app.utils.pugongying_fields import _pick_kol_id
from app.utils.xingtu_fields import _is_valid_star_id, _pick_star_id

XINGTU_DISPLAY_NAME_KEYS = ("nick_name", "nickname", "author_name", "name")
PGY_DISPLAY_NAME_KEYS = ("nick_name", "nickname", "name", "user_name", "kol_name", "blogger_name")


def resolve_xingtu_platform_uid(item: dict[str, Any]) -> str | None:
    """解析星图达人 star_id（字段 id），不使用 core_user_id 等抖音 UID"""
    star = _pick_star_id(item)
    if star:
        return star

    for key in ("id", "author_id", "star_id"):
        val = item.get(key)
        if val is None or str(val).strip() == "":
            continue
        text = str(val).strip()
        if _is_valid_star_id(text):
            return text

    for block_key in ("author", "star_info", "author_info", "user_info"):
        block = item.get(block_key)
        if isinstance(block, dict):
            uid = resolve_xingtu_platform_uid(block)
            if uid:
                return uid
    return None


def resolve_pugongying_platform_uid(item: dict[str, Any]) -> str | None:
    return _pick_kol_id(item)


def pick_display_nickname(item: dict[str, Any], platform: str) -> str:
    keys = PGY_DISPLAY_NAME_KEYS if platform == "xiaohongshu" else XINGTU_DISPLAY_NAME_KEYS
    for key in keys:
        val = item.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()

    for block_key in ("author", "star_info", "author_info", "kol", "blogger", "user"):
        block = item.get(block_key)
        if isinstance(block, dict):
            name = pick_display_nickname(block, platform)
            if name:
                return name
    return ""


def normalize_xingtu_authors(authors: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """合并 _nick: 占位键到真实 UID，丢弃无法解析 ID 的条目"""
    from app.utils.xingtu_fields import merge_author_items

    normalized: dict[str, dict[str, Any]] = {}
    nick_only: list[dict[str, Any]] = []

    for key, item in authors.items():
        if str(key).startswith("_nick:"):
            nick_item = dict(item)
            if not pick_display_nickname(nick_item, "douyin"):
                nick_item["nick_name"] = str(key)[6:]
            nick_only.append(nick_item)
            continue

        uid = resolve_xingtu_platform_uid(item)
        if not uid and str(key).isdigit() and len(str(key)) >= 8:
            uid = str(key)
        if not uid:
            continue

        if uid in normalized:
            normalized[uid] = merge_author_items(normalized[uid], item)
        else:
            normalized[uid] = item

    for item in nick_only:
        nickname = pick_display_nickname(item, "douyin")
        if not nickname:
            continue
        matched_uid = next(
            (
                uid
                for uid, author in normalized.items()
                if pick_display_nickname(author, "douyin") == nickname
            ),
            None,
        )
        if matched_uid:
            normalized[matched_uid] = merge_author_items(normalized[matched_uid], item)

    return normalized
