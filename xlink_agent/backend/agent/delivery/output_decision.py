"""输出决策控制器：放行 / 加声明 / 重试 / 抢救 / 拒绝。"""

from __future__ import annotations

from dataclasses import dataclass

from agent.answer import (
    ensure_knowledge_disclaimer,
    is_count_list_goal,
    is_honest_shortfall_answer,
    is_thin_list_draft,
    is_title_only_list_answer,
    rescue_count_list_answer,
)
from agent.memory_policy import answer_relevant_to_goal

from agent.delivery.types import (
    MaterialStrength,
    OutputAction,
    RequestProfile,
)
from agent.delivery_gate import DeliveryVerdict
from agent.safety import SAFETY_REFUSAL


@dataclass
class Decision:
    action: OutputAction
    text: str
    path: str = ""
    reason: str = ""


def decide_output(
    *,
    goal: str,
    answer: str,
    draft: str,
    verdict: DeliveryVerdict,
    materials: MaterialStrength,
    profile: RequestProfile | None = None,
) -> Decision:
    """根据门控结果与材料强度决定处置。"""
    if verdict.reason == "safety_refuse" or not verdict.ok and verdict.hint == SAFETY_REFUSAL:
        return Decision(OutputAction.REFUSE, SAFETY_REFUSAL, path="safety_refusal", reason="safety")

    text = (answer or "").strip()

    if verdict.ok:
        if materials in {MaterialStrength.EMPTY, MaterialStrength.WEAK, MaterialStrength.OFF_TOPIC}:
            return Decision(
                OutputAction.PASS_WITH_DISCLAIMER,
                ensure_knowledge_disclaimer(text),
                path="pass_with_disclaimer",
                reason=materials.value,
            )
        return Decision(OutputAction.PASS, text, path="pass", reason=verdict.reason or "ok")

    # 结构薄清单 / 条数不足 → 触发重试扩写
    if verdict.reason in {"thin_list", "hollow", "count_shortfall"}:
        return Decision(
            OutputAction.RETRY_EXPAND,
            text or draft,
            path="retry_expand",
            reason=verdict.reason,
        )

    # 鹦鹉 / 错类型 / 模板 → 抢救草稿条目
    if verdict.reason in {
        "parrot_titles",
        "wrong_item_type",
        "fabricated_template",
        "series_padding",
        "duplicate_items",
        "poor_grounding",
    }:
        # 当前答案已是充实详写时勿抢救成薄清单（建议段重复书名等误杀）
        if (
            text
            and not is_title_only_list_answer(text, goal=goal)
            and not is_thin_list_draft(text)
            and answer_relevant_to_goal(text, goal)
        ):
            return Decision(
                OutputAction.PASS_WITH_DISCLAIMER,
                ensure_knowledge_disclaimer(text),
                path="rich_survive_false_gate",
                reason=verdict.reason,
            )
        if is_count_list_goal(goal) and (draft or "").count("《") >= 3:
            return Decision(
                OutputAction.RESCUE_DRAFT,
                draft,
                path="rescue_draft",
                reason=verdict.reason,
            )
        if is_honest_shortfall_answer(text):
            return Decision(
                OutputAction.PASS_WITH_DISCLAIMER,
                ensure_knowledge_disclaimer(text),
                path="honest_shortfall",
                reason=verdict.reason,
            )
        return Decision(
            OutputAction.RETRY_EXPAND,
            draft or text,
            path="retry_expand",
            reason=verdict.reason,
        )

    # 其它失败：有草稿则抢救
    if draft and not is_title_only_list_answer(draft, goal=goal) and not is_thin_list_draft(draft):
        return Decision(OutputAction.PASS_WITH_DISCLAIMER, ensure_knowledge_disclaimer(draft), path="draft_fallback")
    if is_count_list_goal(goal) and (draft or text):
        rescued = rescue_count_list_answer(draft or text, goal=goal, facts=None)
        return Decision(OutputAction.RESCUE_DRAFT, rescued, path="rescue_titles", reason=verdict.reason)

    return Decision(
        OutputAction.PASS_WITH_DISCLAIMER,
        ensure_knowledge_disclaimer(text or draft or "本轮未能整理出可核验答复，请换个问法再试。"),
        path="last_resort",
        reason=verdict.reason,
    )
