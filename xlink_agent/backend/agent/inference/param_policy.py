"""推理参数策略：按风险 × 意图 × A·B·C 档位设置 temperature / 重试预算。"""

from __future__ import annotations

from dataclasses import dataclass

from agent.delivery.types import DeliveryIntent, FactRisk, FactTier, RequestProfile


@dataclass(frozen=True)
class InferenceParams:
    temperature: float = 0.3
    retry_budget: int = 1
    top_p: float | None = None
    force_search: bool = False
    post_scan: bool = False


def params_for_profile(profile: RequestProfile | None, *, phase: str = "synthesize") -> InferenceParams:
    """phase: synthesize | expand_retry | react | verify"""
    if profile is None:
        return InferenceParams(temperature=0.3 if phase != "react" else 0.2, retry_budget=1)

    risk = profile.risk
    intent = profile.intent
    tier = getattr(profile, "tier", FactTier.B) or FactTier.B
    force_search = tier == FactTier.A
    post_scan = tier == FactTier.A

    if phase == "react":
        if tier == FactTier.A:
            temp = 0.12
        elif tier == FactTier.C:
            temp = 0.35
        else:
            temp = 0.15 if risk == FactRisk.HIGH else 0.2
        return InferenceParams(
            temperature=temp,
            retry_budget=1,
            force_search=force_search,
            post_scan=post_scan,
        )

    if phase == "verify":
        return InferenceParams(
            temperature=0.15 if tier == FactTier.A else 0.2,
            retry_budget=0,
            force_search=force_search,
            post_scan=post_scan,
        )

    if phase == "expand_retry":
        if tier == FactTier.A:
            temp = 0.22
        elif risk == FactRisk.HIGH:
            temp = 0.3
        else:
            temp = 0.45
        budget = 2 if intent == DeliveryIntent.LIST_RECOMMEND or tier == FactTier.A else 1
        return InferenceParams(
            temperature=temp,
            retry_budget=budget,
            force_search=force_search,
            post_scan=post_scan,
        )

    # synthesize
    if tier == FactTier.A:
        temp = 0.15
        budget = 2 if intent == DeliveryIntent.LIST_RECOMMEND else 1
    elif risk == FactRisk.HIGH:
        temp = 0.2
        budget = 1
    elif tier == FactTier.C or risk == FactRisk.LOW:
        temp = 0.45
        budget = 1
    else:
        temp = 0.35
        budget = 2 if intent == DeliveryIntent.LIST_RECOMMEND else 1

    if intent == DeliveryIntent.LIST_RECOMMEND and phase == "synthesize":
        budget = max(budget, 2)

    return InferenceParams(
        temperature=temp,
        retry_budget=budget,
        force_search=force_search,
        post_scan=post_scan,
    )
