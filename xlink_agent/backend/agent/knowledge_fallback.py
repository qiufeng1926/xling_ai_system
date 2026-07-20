"""工具失败后的通用知识兜底（不按业务场景特判）。"""

from __future__ import annotations

from typing import Any

from agent.memory_policy import fact_relevant_to_goal


async def knowledge_fallback_answer(model: Any, goal: str) -> str:
    """当工具 Observation 仍不足以作答时，用模型常识给出可读答复。

    不做「天气专属 / 书单专属」分支；只要求：贴合当前问题、不编造需实时核验的精确数据、不 JSON。
    """
    messages = [
        {
            "role": "system",
            "content": (
                "你是通用中文助手。"
                "此刻外网工具结果不足或不可用，请依据常识与稳定知识尽力回答用户。"
                "规则：\n"
                "1. 只回答当前问题，不要夹带无关话题。\n"
                "2. 需要实时数据却无法核验时：说明限制，并给出可操作的下一步，不要编造精确数字。\n"
                "3. 主观判断/推荐类问题可以基于通行知识作答，并标明「供参考」。\n"
                "4. 答复要充分：总起 + 编号列表；每条「标题 + 3～5 句说明」，"
                "不要只给标题清单。\n"
                "5. 禁止让用户回复编号或选一条再展开；一次写完可读终稿。\n"
                "6. 输出普通人能直接读的中文，禁止 JSON / 工具名 / 内部步骤。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"用户问题：{goal}\n\n"
                "请给出信息充分、可直接阅读的中文答复。"
            ),
        },
    ]
    try:
        text = await model.chat(messages, temperature=0.45)
    except Exception:
        return (
            "这一轮没能用工具拿到足够材料，我也暂时没法生成可靠答复。"
            "请稍后再试，或把需求说得更具体一点。"
        )
    text = (text or "").strip()
    return text or "这一轮没有整理出有效答案，请换个说法再试一次。"


def needs_knowledge_fallback(goal: str, facts: list[str], rounds_done: int) -> bool:
    """任意任务：工具跑了若干轮仍无与目标相关的事实 → 允许常识兜底。"""
    relevant = [f for f in facts if fact_relevant_to_goal(f, goal)]
    if relevant:
        return False
    # 给工具足够尝试机会，再兜底（不区分场景）
    return rounds_done >= 2
