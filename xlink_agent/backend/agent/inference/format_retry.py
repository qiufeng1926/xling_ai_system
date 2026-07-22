"""格式 / 薄清单重试控制器。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from agent.answer import (
    answer_keeps_draft_titles,
    is_count_list_goal,
    is_thin_list_draft,
    is_title_only_list_answer,
    sanitize_public_answer,
    strip_pick_number_prompts,
)
from agent.delivery.types import DeliveryIntent, RequestProfile
from agent.inference.param_policy import params_for_profile
from agent.prompts.assembler import assemble_synthesize_system
from agent.prompts.registry import load_template


RewriteFn = Callable[[str, float], Awaitable[str]]


def needs_format_retry(text: str, *, goal: str, profile: RequestProfile | None) -> bool:
    """是否因结构/薄清单不合格需要重试。"""
    t = (text or "").strip()
    if not t:
        return True
    intent = profile.intent if profile else None
    if intent == DeliveryIntent.LIST_RECOMMEND or is_count_list_goal(goal):
        return is_title_only_list_answer(t, goal=goal) or is_thin_list_draft(t)
    return is_thin_list_draft(t) and len(t) < 120


async def format_retry_expand(
    model: Any,
    *,
    goal: str,
    draft: str,
    current: str,
    profile: RequestProfile | None,
    max_retries: int | None = None,
) -> tuple[str, int]:
    """薄清单 / 缺结构时自动重试扩写；返回 (text, retries_used)。"""
    params = params_for_profile(profile, phase="expand_retry")
    budget = max_retries if max_retries is not None else params.retry_budget
    out = sanitize_public_answer(current or "")
    used = 0
    if not needs_format_retry(out, goal=goal, profile=profile):
        return out, 0

    system = assemble_synthesize_system(profile=profile)
    retry_hint = load_template("finalize_list") or "请把标题清单扩写成带短评的可读答复。"

    for _ in range(max(0, budget)):
        if not needs_format_retry(out, goal=goal, profile=profile):
            break
        used += 1
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    f"用户目标：{goal}\n"
                    f"{retry_hint}\n\n"
                    f"草稿条目来源：\n{(draft or out)[:2500]}\n\n"
                    f"不合格的上一版：\n{out[:2000]}\n\n"
                    "请输出合格的详细中文答案。"
                ),
            },
        ]
        try:
            text2 = await model.chat(messages, temperature=params.temperature)
        except Exception:
            break
        cand = strip_pick_number_prompts(sanitize_public_answer(text2 or ""))
        if not cand:
            continue
        if is_count_list_goal(goal) or (
            profile and profile.intent == DeliveryIntent.LIST_RECOMMEND
        ):
            if not answer_keeps_draft_titles(cand, draft or out, goal=goal):
                # 丢条目则不采用，继续重试
                if not needs_format_retry(cand, goal=goal, profile=profile) and len(cand) > len(out):
                    out = cand
                continue
        if not needs_format_retry(cand, goal=goal, profile=profile) or len(cand) > len(out) + 80:
            out = cand
    return out, used
