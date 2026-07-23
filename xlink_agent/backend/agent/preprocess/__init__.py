"""请求预处理入口：产出 RequestProfile。"""

from __future__ import annotations

from agent.delivery.types import RequestProfile
from agent.memory_policy import classify_intent as classify_office_intent
from agent.preprocess.entities import extract_delivery_entities
from agent.preprocess.fact_tier import classify_fact_tier, sync_risk_with_tier
from agent.preprocess.intent import classify_delivery_intent
from agent.preprocess.query_rewrite import build_search_queries, clean_goal_text
from agent.preprocess.risk import classify_fact_risk


def build_request_profile(goal: str, *, draft: str = "") -> RequestProfile:
    """串联意图 / 风险 / A·B·C 档位 / 实体 / 检索 query。"""
    cleaned = clean_goal_text(goal)
    intent = classify_delivery_intent(cleaned)
    risk = classify_fact_risk(cleaned, intent=intent)
    tier = classify_fact_tier(cleaned, intent=intent, risk=risk)
    risk = sync_risk_with_tier(risk, tier)
    entities = extract_delivery_entities(cleaned, draft=draft)
    profile = RequestProfile(
        goal=cleaned,
        intent=intent,
        risk=risk,
        tier=tier,
        entities=entities,
        office_intent=classify_office_intent(cleaned),
        raw={"fact_tier": tier.value},
    )
    profile.search_queries = build_search_queries(profile)
    return profile
