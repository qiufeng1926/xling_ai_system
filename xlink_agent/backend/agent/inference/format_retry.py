"""格式 / 薄清单 / 条数不足 重试控制器。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from agent.answer import (
    answer_keeps_draft_titles,
    count_list_items_in_text,
    is_count_list_goal,
    is_count_shortfall,
    is_thin_list_draft,
    is_title_only_list_answer,
    min_acceptable_list_count,
    requested_list_count,
    sanitize_public_answer,
    strip_pick_number_prompts,
)
from agent.delivery.types import DeliveryIntent, RequestProfile
from agent.inference.param_policy import params_for_profile
from agent.prompts.assembler import assemble_synthesize_system
from agent.prompts.registry import load_template


RewriteFn = Callable[[str, float], Awaitable[str]]


def needs_format_retry(text: str, *, goal: str, profile: RequestProfile | None) -> bool:
    """是否因结构/薄清单/条数不足需要重试。"""
    t = (text or "").strip()
    if not t:
        return True
    intent = profile.intent if profile else None
    if intent == DeliveryIntent.LIST_RECOMMEND or is_count_list_goal(goal):
        if is_count_shortfall(t, goal):
            return True
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
    """薄清单 / 缺结构 / 条数不足时自动重试；返回 (text, retries_used)。"""
    params = params_for_profile(profile, phase="expand_retry")
    budget = max_retries if max_retries is not None else params.retry_budget
    # 条数不足时至少再试 2 轮
    if is_count_shortfall(current or "", goal):
        budget = max(budget, 2)
    out = sanitize_public_answer(current or "")
    used = 0
    if not needs_format_retry(out, goal=goal, profile=profile):
        return out, 0

    system = assemble_synthesize_system(profile=profile)
    n_want = requested_list_count(goal) or 0
    min_n = min_acceptable_list_count(goal) or 0
    list_hint = load_template("finalize_list") or "请把标题清单扩写成带短评的可读答复。"
    shortfall = is_count_shortfall(out, goal)

    for _ in range(max(0, budget)):
        if not needs_format_retry(out, goal=goal, profile=profile):
            break
        used += 1
        if is_count_shortfall(out, goal) or shortfall:
            retry_body = (
                f"用户目标：{goal}\n"
                f"上一版条目数不足（当前约 {count_list_items_in_text(out, goal=goal)} 条，"
                f"目标约 {n_want} 条，至少应有 {min_n} 条）。\n"
                "请重写完整清单：补齐到接近目标条数，每条 2～3 句说明，可分板块；"
                "不足部分可用常识补齐，文首写「以下内容未充分联网核实，仅供常识参考：」。\n"
                "禁止只交 1～2 条详写交差。\n\n"
                f"{list_hint}\n\n"
                f"草稿/线索：\n{(draft or out)[:2500]}\n\n"
                f"不合格的上一版：\n{out[:1800]}\n\n"
                "请输出合格的详细中文答案。"
            )
        else:
            retry_body = (
                f"用户目标：{goal}\n"
                f"{list_hint}\n\n"
                f"草稿条目来源：\n{(draft or out)[:2500]}\n\n"
                f"不合格的上一版：\n{out[:2000]}\n\n"
                "请输出合格的详细中文答案。"
            )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": retry_body},
        ]
        try:
            text2 = await model.chat(messages, temperature=params.temperature)
        except Exception:
            break
        cand = strip_pick_number_prompts(sanitize_public_answer(text2 or ""))
        if not cand:
            continue
        # 补齐条数场景：以条数提升为准，不要求「只保留草稿旧条目」
        if is_count_shortfall(out, goal) or shortfall:
            if count_list_items_in_text(cand, goal=goal) > count_list_items_in_text(
                out, goal=goal
            ):
                out = cand
            continue
        if is_count_list_goal(goal) or (
            profile and profile.intent == DeliveryIntent.LIST_RECOMMEND
        ):
            if not answer_keeps_draft_titles(cand, draft or out, goal=goal):
                if not needs_format_retry(cand, goal=goal, profile=profile) and len(cand) > len(
                    out
                ):
                    out = cand
                continue
        if not needs_format_retry(cand, goal=goal, profile=profile) or len(cand) > len(out) + 80:
            out = cand
    return out, used
