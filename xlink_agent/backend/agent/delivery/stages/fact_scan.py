"""A 类轻量后置扫描：模板硬凑 / 重复 / 薄简介；不绑定具体领域。"""

from __future__ import annotations

from dataclasses import dataclass

from agent.answer import (
    is_count_list_goal,
    is_duplicate_heavy_list,
    is_series_padding_list,
    is_template_fabricated_list,
    is_thin_list_draft,
    is_title_only_list_answer,
    sanitize_hallucinated_list_answer,
)
from agent.delivery.types import FactTier, RequestProfile


@dataclass
class FactScanResult:
    text: str
    cleaned: bool = False
    reasons: list[str] | None = None


def light_fact_scan(
    text: str,
    *,
    goal: str,
    profile: RequestProfile | None,
    facts: list[str] | None = None,
) -> FactScanResult:
    """仅对 A 类启用的轻量扫描；B/C 原样返回。"""
    t = (text or "").strip()
    if not t:
        return FactScanResult(text=t)
    tier = getattr(profile, "tier", None) if profile else None
    if tier != FactTier.A:
        return FactScanResult(text=t)

    reasons: list[str] = []
    if is_template_fabricated_list(t, goal=goal):
        reasons.append("fabricated_template")
    if is_duplicate_heavy_list(t):
        reasons.append("duplicate_items")
    if is_series_padding_list(t):
        reasons.append("series_padding")
    if is_count_list_goal(goal) and (
        is_title_only_list_answer(t, goal=goal) or is_thin_list_draft(t)
    ):
        reasons.append("thin_list")

    if not reasons:
        return FactScanResult(text=t)

    cleaned = sanitize_hallucinated_list_answer(t, goal=goal, facts=facts)
    if cleaned and cleaned != t:
        return FactScanResult(text=cleaned, cleaned=True, reasons=reasons)
    return FactScanResult(text=t, cleaned=False, reasons=reasons)
