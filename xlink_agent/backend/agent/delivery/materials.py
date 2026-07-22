"""材料强度评估（第一期：usable / weak / off_topic / empty）。"""

from __future__ import annotations

from agent.answer import materials_usable_for_goal
from agent.delivery.types import MaterialStrength, RequestProfile


def assess_materials(facts: list[str] | None, profile: RequestProfile) -> MaterialStrength:
    facts = facts or []
    if not facts:
        return MaterialStrength.EMPTY
    goal = profile.goal
    if materials_usable_for_goal(facts, goal):
        return MaterialStrength.USABLE
    # 有事实但不可用：区分跑题与过弱
    blob = "\n".join(facts)
    if len(blob) < 80:
        return MaterialStrength.WEAK
    # 有搜索壳或正文但题型不支撑
    if any(f.startswith("搜索结果") or "网页正文" in f[:20] for f in facts):
        return MaterialStrength.OFF_TOPIC
    return MaterialStrength.WEAK
