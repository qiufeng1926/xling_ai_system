"""采集关键词相关性评分与过滤"""

from __future__ import annotations

import re
from typing import Any

MIN_KEYWORD_MATCH_SCORE = 20.0


def split_keyword_terms(keyword: str) -> list[str]:
    keyword = (keyword or "").strip()
    if not keyword:
        return []
    return [t for t in re.split(r"[,，、\s/|]+", keyword) if t]


def collect_match_haystacks(
    nickname: str,
    tags: list[str],
    extra_data: dict[str, Any] | None = None,
) -> list[str]:
    haystacks: list[str] = []
    if nickname:
        haystacks.append(nickname)
    haystacks.extend(str(t) for t in tags if t)

    extra = extra_data or {}
    parsed = extra.get("parsed") or {}
    for key in ("content_styles", "persona_traits", "creator_type"):
        val = parsed.get(key)
        if isinstance(val, list):
            haystacks.extend(str(v) for v in val if v)
        elif val:
            haystacks.append(str(val))

    for raw_key in ("xingtu_raw", "pugongying_raw"):
        raw = extra.get(raw_key) or {}
        for key in (
            "content_tags",
            "category_tags",
            "tags",
            "tag_list",
            "creator_type",
            "content_theme",
            "nick_name",
            "nickname",
        ):
            val = raw.get(key)
            if isinstance(val, list):
                for entry in val:
                    if isinstance(entry, dict):
                        name = entry.get("name") or entry.get("tag_name")
                        if name:
                            haystacks.append(str(name))
                    elif entry:
                        haystacks.append(str(entry))
            elif val:
                haystacks.append(str(val))
    return [h for h in haystacks if str(h).strip()]


def _term_matches(term: str, hay: str) -> bool:
    term_lower = term.lower()
    hay_lower = hay.lower()
    if term_lower in hay_lower:
        return True
    if len(term) >= 2:
        for i in range(len(term) - 1):
            if term[i : i + 2].lower() in hay_lower:
                return True
    return False


def calc_keyword_match_score(
    keyword: str,
    nickname: str,
    tags: list[str],
    extra_data: dict[str, Any] | None = None,
) -> float:
    terms = split_keyword_terms(keyword)
    if not terms:
        return 50.0

    haystacks = collect_match_haystacks(nickname, tags, extra_data)
    if not haystacks:
        return 0.0

    hay_lower = [h.lower() for h in haystacks]
    nick_lower = nickname.lower() if nickname else ""

    score = 0.0
    matched_terms = 0
    for term in terms:
        term_lower = term.lower()
        best = 0.0
        for h in hay_lower:
            if not _term_matches(term, h):
                continue
            if h == nick_lower or term_lower == h:
                best = max(best, 50.0)
            elif term_lower in h:
                best = max(best, 40.0)
            else:
                best = max(best, 25.0)
        if best > 0:
            score += best
            matched_terms += 1

    if matched_terms == len(terms) and len(terms) > 1:
        score += 15.0

    return round(min(score, 100.0), 2)


def passes_keyword_match(
    keyword: str,
    nickname: str,
    tags: list[str],
    extra_data: dict[str, Any] | None = None,
    *,
    min_score: float = MIN_KEYWORD_MATCH_SCORE,
) -> bool:
    if not split_keyword_terms(keyword):
        return True
    return calc_keyword_match_score(keyword, nickname, tags, extra_data) >= min_score
