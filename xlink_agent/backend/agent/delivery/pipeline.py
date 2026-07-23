"""交付流水线：预处理 → 综合 → 格式重试 → 门控 → 输出决策。"""

from __future__ import annotations

import logging
import re
from typing import Any

from agent.answer import (
    answer_keeps_draft_titles,
    enrich_finish_answer,
    ensure_knowledge_disclaimer,
    is_count_list_goal,
    is_hollow_answer,
    is_substantive_draft,
    is_thin_list_draft,
    is_title_only_list_answer,
    looks_like_internal,
    rescue_count_list_answer,
    sanitize_hallucinated_list_answer,
    sanitize_public_answer,
    strip_pick_number_prompts,
    synthesize_rich_answer,
)
from agent.context import TaskContext
from agent.delivery.materials import assess_materials
from agent.delivery.output_decision import decide_output
from agent.delivery.stages.format_normalize import format_normalize
from agent.delivery.types import (
    DeliveryContext,
    DeliveryIntent,
    DeliveryResult,
    MaterialStrength,
    OutputAction,
)
from agent.delivery_gate import get_default_delivery_gate
from agent.inference.format_retry import format_retry_expand
from agent.inference.param_policy import params_for_profile
from agent.knowledge_fallback import knowledge_fallback_answer
from agent.memory_policy import answer_relevant_to_goal
from agent.preprocess import build_request_profile
from agent.run_state import FinalizePath
from agent.safety import (
    SAFETY_REFUSAL,
    answer_contains_prohibited_detail,
    enforce_safety_answer,
    is_disallowed_request,
    is_safety_refusal,
)

logger = logging.getLogger("xlink-agent.orchestrator")


def _reject_internal(text: str, goal: str) -> str:
    t = sanitize_public_answer(text or "")
    if looks_like_internal(t):
        return ""
    return t


async def run_delivery_pipeline(
    model: Any,
    task_ctx: TaskContext,
    content: str,
    *,
    round_i: int = 0,
    thought: str = "",
    run_state: Any | None = None,
) -> str:
    """主入口：替代 orchestrator._finalize_user_answer 的分支树。"""
    goal = task_ctx.goal or ""
    gate = get_default_delivery_gate()

    if is_disallowed_request(goal):
        return _record(run_state, FinalizePath.SAFETY_REFUSAL, SAFETY_REFUSAL, round_i)

    seed = content or ""
    if run_state is not None:
        saved = getattr(run_state, "react_finish_draft", "") or ""
        if saved and (
            is_hollow_answer(seed)
            or is_thin_list_draft(seed)
            or is_title_only_list_answer(seed, goal=goal)
        ):
            seed = saved

    draft = enrich_finish_answer(seed, thought=thought, facts=task_ctx.facts, goal=goal)
    draft = strip_pick_number_prompts(_reject_internal(draft, goal) or draft or "")

    if is_safety_refusal(draft) or answer_contains_prohibited_detail(draft):
        return _record(run_state, FinalizePath.SAFETY_REFUSAL, SAFETY_REFUSAL, round_i)

    profile = build_request_profile(goal, draft=draft)
    materials = assess_materials(task_ctx.facts, profile)
    ctx = DeliveryContext(
        goal=goal,
        draft=draft,
        thought=thought,
        facts=list(task_ctx.facts or []),
        profile=profile,
        materials=materials,
        round_i=round_i,
        run_state=run_state,
    )

    # 安全门（goal 级）
    rv = gate.check_final(goal=goal, answer=draft or "x", facts=task_ctx.facts)
    if rv.reason == "safety_refuse":
        return _record(run_state, FinalizePath.SAFETY_REFUSAL, SAFETY_REFUSAL, round_i)

    force_expand = (
        profile.intent == DeliveryIntent.LIST_RECOMMEND
        or is_count_list_goal(goal)
        or is_thin_list_draft(draft)
        or is_title_only_list_answer(draft, goal=goal)
        or materials != MaterialStrength.USABLE
    )

    # 有足够条目的清单：优先详写，禁止直接交标题堆
    listish = is_count_list_goal(goal) or profile.intent == DeliveryIntent.LIST_RECOMMEND
    rescued = ""
    if listish and (draft or "").count("《") >= 3:
        rescued = rescue_count_list_answer(draft, goal=goal, facts=task_ctx.facts)

    params = params_for_profile(profile, phase="synthesize")
    rich = await synthesize_rich_answer(
        model,
        goal=goal,
        facts=task_ctx.facts if materials == MaterialStrength.USABLE else [],
        draft=draft,
        thought=thought,
        force_expand=bool(force_expand),
        profile=profile,
        temperature=params.temperature,
    )
    text = _reject_internal(rich, goal)
    text = format_normalize(
        text,
        materials=materials,
        force_disclaimer=materials != MaterialStrength.USABLE,
    )

    # 格式重试（含条数不足补齐）
    from agent.answer import is_count_shortfall

    text, retries = await format_retry_expand(
        model,
        goal=goal,
        draft=draft,
        current=text,
        profile=profile,
        max_retries=max(params.retry_budget, 2 if is_count_shortfall(text, goal) else params.retry_budget),
    )
    text = format_normalize(text, materials=materials)

    # 清单：扩写仍薄或丢条目 → 空材料再扩一轮
    if listish and draft.count("《") >= 5:
        if (
            is_title_only_list_answer(text, goal=goal)
            or not answer_keeps_draft_titles(text, draft, goal=goal)
        ):
            rich2 = await synthesize_rich_answer(
                model,
                goal=goal,
                facts=[],
                draft=draft,
                thought=thought,
                force_expand=True,
                profile=profile,
                temperature=params.temperature,
            )
            cand = format_normalize(_reject_internal(rich2, goal), materials=MaterialStrength.EMPTY)
            cand, r2 = await format_retry_expand(
                model, goal=goal, draft=draft, current=cand, profile=profile
            )
            retries += r2
            if answer_keeps_draft_titles(cand, draft, goal=goal) and not is_title_only_list_answer(
                cand, goal=goal
            ):
                text = format_normalize(cand, materials=MaterialStrength.EMPTY)

    verdict = gate.check_final(goal=goal, answer=text, facts=task_ctx.facts)
    # 允许：充实详答被门控误杀（thin / 假重复 / 假模板）时放行
    if not verdict.ok and verdict.reason in {
        "thin_list",
        "duplicate_items",
        "fabricated_template",
    }:
        if (
            not is_title_only_list_answer(text, goal=goal)
            and not is_thin_list_draft(text)
            and not is_count_shortfall(text, goal)
            and answer_relevant_to_goal(text, goal)
        ):
            verdict = type(verdict)(True, "structure_ok_override", verdict.hint)

    decision = decide_output(
        goal=goal,
        answer=text,
        draft=draft,
        verdict=verdict,
        materials=materials,
        profile=profile,
    )

    if decision.action == OutputAction.REFUSE:
        return _record(run_state, FinalizePath.SAFETY_REFUSAL, SAFETY_REFUSAL, round_i)

    if decision.action == OutputAction.RETRY_EXPAND:
        rich3 = await synthesize_rich_answer(
            model,
            goal=goal,
            facts=[] if materials != MaterialStrength.USABLE else task_ctx.facts,
            draft=draft or text,
            thought=thought,
            force_expand=True,
            profile=profile,
            temperature=params.temperature,
        )
        text = format_normalize(_reject_internal(rich3, goal), materials=materials)
        text, r3 = await format_retry_expand(
            model, goal=goal, draft=draft, current=text, profile=profile
        )
        retries += r3
        verdict = gate.check_final(goal=goal, answer=text, facts=task_ctx.facts)
        decision = decide_output(
            goal=goal,
            answer=text,
            draft=draft,
            verdict=verdict,
            materials=materials,
            profile=profile,
        )

    if decision.action == OutputAction.RESCUE_DRAFT:
        # 已有充实详答时禁止冲成薄标题清单（门控误杀 duplicate/template 时）
        if (
            text
            and not is_title_only_list_answer(text, goal=goal)
            and not is_thin_list_draft(text)
            and not is_count_shortfall(text, goal)
            and answer_relevant_to_goal(text, goal)
        ):
            return _track_deliver(
                run_state,
                FinalizePath.DRAFT_EXPANDED,
                ensure_knowledge_disclaimer(text),
                goal=goal,
                facts=task_ctx.facts,
                materials=materials,
                round_i=round_i,
                retries=retries,
            )
        # 再尝试详写；失败才交标题抢救
        rich4 = await synthesize_rich_answer(
            model,
            goal=goal,
            facts=[],
            draft=draft,
            thought=thought,
            force_expand=True,
            profile=profile,
            temperature=params.temperature,
        )
        cand = format_normalize(_reject_internal(rich4, goal), materials=MaterialStrength.EMPTY)
        cand, r4 = await format_retry_expand(
            model, goal=goal, draft=draft, current=cand, profile=profile
        )
        retries += r4
        if (
            cand
            and answer_relevant_to_goal(cand, goal)
            and (
                not listish
                or (
                    answer_keeps_draft_titles(cand, draft, goal=goal)
                    and not is_title_only_list_answer(cand, goal=goal)
                )
            )
        ):
            text = cand
            path = FinalizePath.DRAFT_EXPANDED
        else:
            text = rescued or rescue_count_list_answer(draft, goal=goal, facts=task_ctx.facts)
            path = FinalizePath.DRAFT_DIRECT_NO_MATERIALS
        return _track_deliver(
            run_state,
            path,
            text,
            goal=goal,
            facts=task_ctx.facts,
            materials=materials,
            round_i=round_i,
            retries=retries,
        )

    text = decision.text
    if decision.action == OutputAction.PASS_WITH_DISCLAIMER:
        text = ensure_knowledge_disclaimer(text)

    # 清洗：充实答复不得压薄
    before = text
    text = sanitize_hallucinated_list_answer(text, goal=goal, facts=task_ctx.facts)
    if params.post_scan:
        from agent.delivery.stages.fact_scan import light_fact_scan

        scanned = light_fact_scan(
            text, goal=goal, profile=profile, facts=task_ctx.facts
        )
        text = scanned.text
        if scanned.cleaned and run_state is not None:
            try:
                run_state.intercept(
                    "fact_tier_post_scan",
                    round_i=round_i,
                    reasons=",".join(scanned.reasons or []),
                )
            except Exception:
                pass
    if (
        listish
        and before.count("《") >= 5
        and (text or "").count("《") < 3
        and rescued
    ):
        text = rescued

    if not text or is_hollow_answer(text):
        if is_substantive_draft(draft, goal, facts=task_ctx.facts):
            text = ensure_knowledge_disclaimer(draft)
            path = FinalizePath.SUBSTANTIVE_BEFORE_FALLBACK
        elif listish:
            text = rescued or rescue_count_list_answer(draft, goal=goal, facts=task_ctx.facts)
            path = FinalizePath.KNOWLEDGE_FALLBACK
        else:
            fb = await knowledge_fallback_answer(model, goal, facts=task_ctx.facts)
            text = ensure_knowledge_disclaimer(_reject_internal(fb or "", goal) or fb or "")
            path = FinalizePath.KNOWLEDGE_FALLBACK
        return _track_deliver(
            run_state,
            path,
            text,
            goal=goal,
            facts=task_ctx.facts,
            materials=materials,
            round_i=round_i,
            retries=retries,
        )

    if retries > 0 and not is_title_only_list_answer(text, goal=goal):
        path = FinalizePath.DRAFT_EXPANDED
    elif materials == MaterialStrength.USABLE and decision.action == OutputAction.PASS:
        path = FinalizePath.RICH_SYNTHESIS
    elif materials != MaterialStrength.USABLE:
        path = (
            FinalizePath.DRAFT_EXPANDED
            if not is_title_only_list_answer(text, goal=goal)
            else FinalizePath.DRAFT_DIRECT_NO_MATERIALS
        )
    else:
        path = FinalizePath.DRAFT_EXPANDED

    return _track_deliver(
        run_state,
        path,
        text,
        goal=goal,
        facts=task_ctx.facts,
        materials=materials,
        round_i=round_i,
        retries=retries,
    )


def _record(run_state, path, text: str, round_i: int) -> str:
    if run_state is not None:
        run_state.record_finalize(path, text, round_i=round_i)
    return text


def _track_deliver(
    run_state,
    path,
    text: str,
    *,
    goal: str,
    facts: list[str],
    materials: MaterialStrength,
    round_i: int,
    retries: int = 0,
) -> str:
    text = enforce_safety_answer(goal=goal, answer=text or "")
    if is_safety_refusal(text):
        return _record(run_state, FinalizePath.SAFETY_REFUSAL, SAFETY_REFUSAL, round_i)
    text = strip_pick_number_prompts(sanitize_public_answer(text))
    if run_state is not None:
        run_state.record_finalize(path, text, round_i=round_i)
        run_state.snapshot_answer(
            "finalize_ctx",
            text,
            round_i=round_i,
            path=path.value if hasattr(path, "value") else str(path),
            has_materials=materials == MaterialStrength.USABLE,
            fact_count=len(facts or []),
        )
        logger.info(
            "deliver[%s] path=%s chars=%s retries=%s preview=%s",
            run_state.run_id[:8],
            path.value if hasattr(path, "value") else path,
            len(text or ""),
            retries,
            re.sub(r"\s+", " ", (text or ""))[:160],
        )
    return text
