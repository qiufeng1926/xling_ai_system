"""交付门控：统一「能否 finish / 草稿是否合格 / 终稿是否可交」。

本轮实现 AnswerQualityGate；后续 SafetyGate 等实现同一 Protocol，
经 compose_gates 串联即可，无需再拆 orchestrator 主循环。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from agent.answer import (
    answer_parrots_search_titles,
    has_substantive_content_facts,
    is_hollow_answer,
    is_thin_list_draft,
    pick_fetch_url,
    sanitize_public_answer,
)


@dataclass
class DeliveryVerdict:
    ok: bool
    reason: str = ""
    hint: str = ""


@runtime_checkable
class DeliveryGate(Protocol):
    def check_research(
        self,
        *,
        goal: str,
        facts: list[str],
        steps: list[Any],
        failed_urls: list[str] | None = None,
    ) -> DeliveryVerdict: ...

    def check_draft(
        self,
        *,
        goal: str,
        draft: str,
        facts: list[str] | None = None,
    ) -> DeliveryVerdict: ...

    def check_final(
        self,
        *,
        goal: str,
        answer: str,
        facts: list[str] | None = None,
    ) -> DeliveryVerdict: ...


class AnswerQualityGate:
    """答题质量门控：调研深度、标题清单、薄列表。"""

    def check_research(
        self,
        *,
        goal: str,
        facts: list[str],
        steps: list[Any],
        failed_urls: list[str] | None = None,
    ) -> DeliveryVerdict:
        from agent.research_policy import (
            count_body_facts,
            count_search_steps,
            has_search_hit_facts,
            is_deep_research_goal,
            min_bodies_for_goal,
            min_searches_for_goal,
        )

        deep = is_deep_research_goal(goal)
        searches = count_search_steps(steps)
        bodies = count_body_facts(facts, goal=goal)
        min_s = min_searches_for_goal(goal)
        min_b = min_bodies_for_goal(goal)
        skip = set(failed_urls or [])

        if deep:
            if searches < min_s:
                return DeliveryVerdict(
                    False,
                    "need_alt_search",
                    hint=f"搜索 {searches}/{min_s}",
                )
            if bodies < min_b:
                next_u = pick_fetch_url(facts, skip=skip, goal=goal)
                if next_u:
                    return DeliveryVerdict(
                        False,
                        "need_more_bodies",
                        hint=f"正文 {bodies}/{min_b}，可抓 {next_u[:60]}",
                    )
                # 无可抓链接：再搜一轮找新源
                if searches < min_s + 1:
                    return DeliveryVerdict(
                        False,
                        "search_for_more_sources",
                        hint=f"正文不足且无链接，需补搜（已搜 {searches}）",
                    )
                # 已尽力：允许 finish，但标记弱材料，由 finalize 强制合成
                return DeliveryVerdict(
                    True,
                    "weak_materials",
                    hint=f"正文 {bodies}/{min_b}，无更多源",
                )
            return DeliveryVerdict(True, "")

        # 浅任务：有 hits 无 body → 必须先抓
        if (
            has_search_hit_facts(facts)
            and bodies < 1
            and not has_substantive_content_facts(facts)
            and pick_fetch_url(facts, skip=skip)
        ):
            return DeliveryVerdict(False, "search_hits_no_body", hint="有搜索命中无正文")
        return DeliveryVerdict(True, "")

    def check_draft(
        self,
        *,
        goal: str,
        draft: str,
        facts: list[str] | None = None,
    ) -> DeliveryVerdict:
        text = sanitize_public_answer(draft or "").strip()
        facts = facts or []
        if not text or is_hollow_answer(text):
            return DeliveryVerdict(False, "hollow", hint="空壳草稿")
        if facts and answer_parrots_search_titles(text, facts):
            return DeliveryVerdict(False, "parrot_titles", hint="草稿复读搜索标题")
        # 无 facts 时也拦截「合集/书单」口吻标题堆
        if answer_parrots_search_titles(text, []) and (
            "合集" in text or "书单" in text or "推荐" in text[:40]
        ):
            return DeliveryVerdict(False, "parrot_titles", hint="合集标题口吻")
        from agent.answer import (
            is_duplicate_heavy_list,
            is_poorly_grounded,
            is_series_padding_list,
            is_template_fabricated_list,
        )

        if is_series_padding_list(text):
            return DeliveryVerdict(False, "series_padding", hint="用同一系列编号硬凑条数")
        if is_duplicate_heavy_list(text):
            return DeliveryVerdict(False, "duplicate_items", hint="列表存在重复条目")
        if is_template_fabricated_list(text, goal=goal):
            return DeliveryVerdict(False, "fabricated_template", hint="疑似模板硬凑伪书名")
        from agent.answer import is_count_list_goal, is_off_type_list_item, _list_item_titles

        if is_count_list_goal(goal):
            items = _list_item_titles(text)
            if items:
                bad = sum(1 for it in items if is_off_type_list_item(it, goal))
                if bad >= max(1, (len(items) + 1) // 2):
                    return DeliveryVerdict(
                        False, "wrong_item_type", hint="条目类型与目标不符"
                    )
        if is_thin_list_draft(text):
            return DeliveryVerdict(False, "thin_list", hint="条目过薄，仅有标题")
        # 有实质检索材料时，拒绝与材料几乎无重合的长文（防幻觉扩写）
        if facts and is_poorly_grounded(text, facts):
            return DeliveryVerdict(False, "poor_grounding", hint="答案与检索材料脱节")
        return DeliveryVerdict(True, "")

    def check_final(
        self,
        *,
        goal: str,
        answer: str,
        facts: list[str] | None = None,
    ) -> DeliveryVerdict:
        # 终稿与草稿同一套质量标准（可交才 ok）
        return self.check_draft(goal=goal, draft=answer, facts=facts)


class _ComposedGate:
    def __init__(self, gates: tuple[DeliveryGate, ...]) -> None:
        self._gates = gates

    def check_research(
        self,
        *,
        goal: str,
        facts: list[str],
        steps: list[Any],
        failed_urls: list[str] | None = None,
    ) -> DeliveryVerdict:
        last_ok = DeliveryVerdict(True, "")
        for g in self._gates:
            v = g.check_research(
                goal=goal, facts=facts, steps=steps, failed_urls=failed_urls
            )
            if not v.ok:
                return v
            if v.reason:
                last_ok = v
        return last_ok

    def check_draft(
        self,
        *,
        goal: str,
        draft: str,
        facts: list[str] | None = None,
    ) -> DeliveryVerdict:
        for g in self._gates:
            v = g.check_draft(goal=goal, draft=draft, facts=facts)
            if not v.ok:
                return v
        return DeliveryVerdict(True, "")

    def check_final(
        self,
        *,
        goal: str,
        answer: str,
        facts: list[str] | None = None,
    ) -> DeliveryVerdict:
        for g in self._gates:
            v = g.check_final(goal=goal, answer=answer, facts=facts)
            if not v.ok:
                return v
        return DeliveryVerdict(True, "")


def compose_gates(*gates: DeliveryGate) -> DeliveryGate:
    """串联多门控：任一失败即拦截；research 上保留最后一个非空 reason（如 weak_materials）。"""
    cleaned = tuple(g for g in gates if g is not None)
    if not cleaned:
        return AnswerQualityGate()
    if len(cleaned) == 1:
        return cleaned[0]
    return _ComposedGate(cleaned)


_default_gate: DeliveryGate | None = None


def get_default_delivery_gate() -> DeliveryGate:
    """编排层默认门控；后续可改为 compose_gates(AnswerQualityGate(), SafetyGate())。"""
    global _default_gate
    if _default_gate is None:
        _default_gate = compose_gates(AnswerQualityGate())
    return _default_gate


def set_default_delivery_gate(gate: DeliveryGate | None) -> None:
    """测试或装配时替换默认门控。"""
    global _default_gate
    _default_gate = gate


def reject_or_pass_final(
    *,
    goal: str,
    answer: str,
    facts: list[str] | None = None,
    gate: DeliveryGate | None = None,
) -> str | None:
    """终稿合格则返回清洗后文本，否则 None。"""
    g = gate or get_default_delivery_gate()
    text = sanitize_public_answer(answer or "").strip()
    if not text:
        return None
    v = g.check_final(goal=goal, answer=text, facts=facts)
    if not v.ok:
        return None
    return text
