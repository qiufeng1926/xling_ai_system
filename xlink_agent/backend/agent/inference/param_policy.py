"""推理参数策略：按风险 × 意图设置 temperature / 重试预算。"""

from __future__ import annotations

from dataclasses import dataclass

from agent.delivery.types import DeliveryIntent, FactRisk, RequestProfile


@dataclass(frozen=True)
class InferenceParams:
    temperature: float = 0.3
    retry_budget: int = 1
    top_p: float | None = None


def params_for_profile(profile: RequestProfile | None, *, phase: str = "synthesize") -> InferenceParams:
    """phase: synthesize | expand_retry | react | verify"""
    if profile is None:
        return InferenceParams(temperature=0.3 if phase != "react" else 0.2, retry_budget=1)

    risk = profile.risk
    intent = profile.intent

    if phase == "react":
        temp = 0.15 if risk == FactRisk.HIGH else 0.2
        return InferenceParams(temperature=temp, retry_budget=1)

    if phase == "verify":
        return InferenceParams(temperature=0.2, retry_budget=0)

    if phase == "expand_retry":
        temp = 0.45 if risk != FactRisk.HIGH else 0.3
        budget = 2 if intent == DeliveryIntent.LIST_RECOMMEND else 1
        return InferenceParams(temperature=temp, retry_budget=budget)

    # synthesize
    if risk == FactRisk.HIGH:
        temp = 0.2
        budget = 1
    elif risk == FactRisk.LOW:
        temp = 0.4
        budget = 1
    else:
        temp = 0.35
        budget = 2 if intent == DeliveryIntent.LIST_RECOMMEND else 1

    if intent == DeliveryIntent.LIST_RECOMMEND and phase == "synthesize":
        budget = max(budget, 2)

    return InferenceParams(temperature=temp, retry_budget=budget)
