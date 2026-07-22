"""安全门控：包装现有 safety 规则。"""

from __future__ import annotations

from typing import Any

from agent.delivery_gate import DeliveryVerdict
from agent.safety import (
    SAFETY_REFUSAL,
    answer_contains_prohibited_detail,
    is_disallowed_request,
    is_safety_refusal,
)


class SafetyGate:
    """违规请求 / 输出泄漏 → 拒绝。"""

    def check_research(
        self,
        *,
        goal: str,
        facts: list[str],
        steps: list[Any],
        failed_urls: list[str] | None = None,
    ) -> DeliveryVerdict:
        if is_disallowed_request(goal or ""):
            return DeliveryVerdict(False, "safety_refuse", hint=SAFETY_REFUSAL)
        return DeliveryVerdict(True, "")

    def check_draft(
        self,
        *,
        goal: str,
        draft: str,
        facts: list[str] | None = None,
    ) -> DeliveryVerdict:
        return self._check(goal=goal, text=draft)

    def check_final(
        self,
        *,
        goal: str,
        answer: str,
        facts: list[str] | None = None,
    ) -> DeliveryVerdict:
        return self._check(goal=goal, text=answer)

    def _check(self, *, goal: str, text: str) -> DeliveryVerdict:
        if is_disallowed_request(goal or ""):
            return DeliveryVerdict(False, "safety_refuse", hint=SAFETY_REFUSAL)
        if is_safety_refusal(text or "") or answer_contains_prohibited_detail(text or ""):
            return DeliveryVerdict(False, "safety_refuse", hint=SAFETY_REFUSAL)
        return DeliveryVerdict(True, "")
