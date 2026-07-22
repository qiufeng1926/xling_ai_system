"""接地门控：有实质材料时答案须与材料有足够重合。"""

from __future__ import annotations

from typing import Any

from agent.answer import (
    has_substantive_content_facts,
    is_count_list_goal,
    is_honest_shortfall_answer,
    is_poorly_grounded,
)
from agent.delivery_gate import DeliveryVerdict


class GroundingGate:
    """材料可用时拒绝严重不接地的长文幻觉。"""

    def check_research(
        self,
        *,
        goal: str,
        facts: list[str],
        steps: list[Any],
        failed_urls: list[str] | None = None,
    ) -> DeliveryVerdict:
        return DeliveryVerdict(True, "")

    def check_draft(
        self,
        *,
        goal: str,
        draft: str,
        facts: list[str] | None = None,
    ) -> DeliveryVerdict:
        return self._check(goal=goal, text=draft, facts=facts)

    def check_final(
        self,
        *,
        goal: str,
        answer: str,
        facts: list[str] | None = None,
    ) -> DeliveryVerdict:
        return self._check(goal=goal, text=answer, facts=facts)

    def _check(
        self,
        *,
        goal: str,
        text: str,
        facts: list[str] | None,
    ) -> DeliveryVerdict:
        facts = facts or []
        if not facts or not has_substantive_content_facts(facts):
            return DeliveryVerdict(True, "")
        if is_poorly_grounded(text or "", facts, goal=goal):
            if is_honest_shortfall_answer(text or ""):
                return DeliveryVerdict(True, "weak_grounding_ok")
            if is_count_list_goal(goal) and (text or "").count("《") >= 5:
                return DeliveryVerdict(True, "list_draft_override")
            return DeliveryVerdict(False, "poor_grounding", hint="答案与检索材料脱节")
        return DeliveryVerdict(True, "")
