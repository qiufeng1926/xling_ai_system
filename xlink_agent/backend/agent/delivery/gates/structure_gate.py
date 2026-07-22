"""结构门控：空壳 / 薄清单 / 鹦鹉标题 / 模板注水。"""

from __future__ import annotations

from typing import Any

from agent.answer import (
    answer_parrots_search_titles,
    is_count_list_goal,
    is_duplicate_heavy_list,
    is_hollow_answer,
    is_off_type_list_item,
    is_series_padding_list,
    is_template_fabricated_list,
    is_thin_list_draft,
    is_title_only_list_answer,
    sanitize_public_answer,
    _list_item_titles,
)
from agent.delivery_gate import DeliveryVerdict


class StructureGate:
    """答题结构质量：薄列表、鹦鹉、模板硬凑。"""

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
        t = sanitize_public_answer(text or "").strip()
        facts = facts or []
        if not t or is_hollow_answer(t):
            return DeliveryVerdict(False, "hollow", hint="空壳草稿")
        if facts and answer_parrots_search_titles(t, facts):
            return DeliveryVerdict(False, "parrot_titles", hint="复读搜索标题")
        if answer_parrots_search_titles(t, []) and (
            "合集" in t or "书单" in t or "推荐" in t[:40]
        ):
            return DeliveryVerdict(False, "parrot_titles", hint="合集标题口吻")
        if is_series_padding_list(t):
            return DeliveryVerdict(False, "series_padding", hint="系列编号硬凑")
        if is_duplicate_heavy_list(t):
            return DeliveryVerdict(False, "duplicate_items", hint="重复条目")
        if is_template_fabricated_list(t, goal=goal):
            return DeliveryVerdict(False, "fabricated_template", hint="模板硬凑")
        if is_count_list_goal(goal):
            items = _list_item_titles(t)
            if items:
                bad = sum(1 for it in items if is_off_type_list_item(it, goal))
                if bad >= max(1, (len(items) + 1) // 2):
                    return DeliveryVerdict(False, "wrong_item_type", hint="条目类型不符")
            if is_title_only_list_answer(t, goal=goal) or is_thin_list_draft(t):
                return DeliveryVerdict(False, "thin_list", hint="条目过薄，仅有标题")
        elif is_thin_list_draft(t):
            return DeliveryVerdict(False, "thin_list", hint="条目过薄，仅有标题")
        return DeliveryVerdict(True, "")
