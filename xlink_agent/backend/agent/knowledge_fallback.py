"""工具失败后的通用知识兜底（不按业务场景特判）。"""

from __future__ import annotations

from typing import Any

from agent.memory_policy import fact_relevant_to_goal

_DISCLAIMER = "以下内容未充分联网核实，仅供常识参考："


async def knowledge_fallback_answer(
    model: Any,
    goal: str,
    *,
    facts: list[str] | None = None,
) -> str:
    """当工具 Observation 仍不足以作答时，用模型常识给出短而诚实的答复。

    明确声明未核实；禁止为凑篇幅编造精确数据或虚构清单。
    """
    from agent.answer import (
        honest_grounded_list_answer,
        is_count_list_goal,
        sanitize_hallucinated_list_answer,
    )

    weak_bits = []
    for f in (facts or [])[:6]:
        if fact_relevant_to_goal(f, goal) and len(f) >= 40:
            weak_bits.append(f[:400])
    materials = "\n".join(weak_bits) if weak_bits else "（无）"

    list_rules = ""
    if is_count_list_goal(goal):
        list_rules = (
            "7. 计数清单特别规则：只写材料或你有把握核验的具体条目；"
            "禁止用「主题词+与/和+后缀」模板连造多条；禁止重复条目凑数；"
            "用户要 N 条而可核验更少时，就少写并写明未凑满；"
            "宁可短，也不要伪条目。\n"
        )

    messages = [
        {
            "role": "system",
            "content": (
                "你是通用中文助手。"
                "此刻外网工具结果不足或不可用。"
                "规则：\n"
                f"1. 文首必须写「{_DISCLAIMER}」。\n"
                "2. 只回答当前问题，不要夹带无关话题。\n"
                "3. 需要实时数据却无法核验：说明限制，并给出可操作的下一步，不要编造精确数字。\n"
                "4. 宁可短而准确：总起 + 少量要点；材料/草稿没有的书名、数据、事件、产品名禁止编造。"
                "若用户要 N 条而你只记得更少，就少写并说明，"
                "禁止用同一系列名加 1～N 编号硬凑条数。\n"
                "5. 禁止让用户回复编号；禁止用通用「学习路径/四步法」模板糊弄任意问题。\n"
                "6. 输出普通人能直接读的中文，禁止 JSON / 工具名 / 内部步骤。\n"
                f"{list_rules}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"用户问题：{goal}\n\n"
                f"本轮仅有的弱线索（可引用则引用，没有则不要扩写）：\n{materials}\n\n"
                "请给出短而诚实的中文答复。"
            ),
        },
    ]
    try:
        text = await model.chat(messages, temperature=0.2)
    except Exception:
        if is_count_list_goal(goal):
            return honest_grounded_list_answer(goal, facts)
        return (
            f"{_DISCLAIMER}\n\n"
            "这一轮没能用工具拿到足够可核验材料，暂不给出可能不准确的细节。"
            "请稍后再试，或把需求说得更具体一点。"
        )
    text = (text or "").strip()
    if not text:
        if is_count_list_goal(goal):
            return honest_grounded_list_answer(goal, facts)
        return (
            f"{_DISCLAIMER}\n\n"
            "这一轮没有整理出有效答案，请换个说法再试一次。"
        )
    if _DISCLAIMER[:8] not in text[:80] and "仅供" not in text[:60]:
        text = f"{_DISCLAIMER}\n\n{text}"
    return sanitize_hallucinated_list_answer(text, goal=goal, facts=facts)


def needs_knowledge_fallback(goal: str, facts: list[str], rounds_done: int) -> bool:
    """任意任务：工具跑了若干轮仍无与目标相关的事实 → 允许常识兜底。

    有搜索命中且仍可抓正文时不触发，避免过早「材料不足」。
    """
    from agent.answer import pick_fetch_url
    from agent.research_policy import count_body_facts, has_search_hit_facts

    if (
        has_search_hit_facts(facts)
        and count_body_facts(facts, goal=goal) < 1
        and pick_fetch_url(facts, goal=goal)
    ):
        return False
    relevant = [f for f in facts if fact_relevant_to_goal(f, goal)]
    if relevant:
        return False
    # 给工具足够尝试机会，再兜底（不区分场景）
    return rounds_done >= 2
