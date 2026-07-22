"""Query 清洗与检索改写（用户不可见）。"""

from __future__ import annotations

import re

from agent.delivery.types import DeliveryIntent, RequestProfile


_NOISE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_MULTI_SPACE = re.compile(r"\s+")


def clean_goal_text(goal: str) -> str:
    """剔除控制字符与多余空白。"""
    t = _NOISE_RE.sub("", goal or "")
    t = _MULTI_SPACE.sub(" ", t).strip()
    return t


def build_search_queries(profile: RequestProfile) -> list[str]:
    """为检索模块生成优化 query 列表。"""
    goal = clean_goal_text(profile.goal)
    if not goal:
        return []

    queries: list[str] = [goal[:80]]
    ents = [e for e in profile.entities if e and e not in goal][:4]

    if profile.intent == DeliveryIntent.LIST_RECOMMEND:
        # 通用清单检索：主题 + 推荐/盘点，不绑定书籍站
        core = re.sub(
            r"(给我|帮我|请|一下|推荐|盘点|清单)",
            " ",
            goal,
        )
        core = _MULTI_SPACE.sub(" ", core).strip()[:40]
        if core:
            queries.append(f"{core} 推荐 清单")
            queries.append(f"{core} 盘点 对比")
    elif profile.intent in {DeliveryIntent.OPEN_QA, DeliveryIntent.RESEARCH}:
        if ents:
            queries.append(" ".join(ents[:3]) + " 概述")
        queries.append(goal[:60] + " 要点")
    elif profile.intent == DeliveryIntent.PLAN_WRITE:
        queries.append(goal[:50] + " 方案 步骤")
    else:
        if ents:
            queries.append(" ".join(ents[:3]))

    # 去重保序
    out: list[str] = []
    seen: set[str] = set()
    for q in queries:
        q = _MULTI_SPACE.sub(" ", (q or "").strip())
        if not q or q in seen:
            continue
        seen.add(q)
        out.append(q[:100])
    return out[:5]
