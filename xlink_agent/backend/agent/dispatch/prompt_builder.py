"""请求组装：系统指令 + 召回片段 + 治理后上下文 + 工具描述。"""

from __future__ import annotations

from typing import Any

from agent.dispatch.types import ContextBundle, DispatchQuery, PromptPackage, TaskTransition
from agent.prompts.assembler import assemble_react_base_addon
from agent.react import REACT_SYSTEM_PROMPT
from agent.safety import SAFETY_POLICY_PROMPT


_OUTPUT_DISCIPLINE = (
    "# 调度层输出规范\n"
    "1. 默认输出完整落地级内容：定义/原理/流程/落地细节按需覆盖；禁止无依据简答与省略关键步骤。\n"
    "2. 对系统注入的「召回历史」须主动甄别：仅采纳与当前用户目标直接相关的条目，弱相关必须忽略。\n"
    "3. 严格遵循工具参数契约；缺参时先补全再调用，禁止空喊已生成文件。\n"
    "4. finish 只给用户可读中文终稿，禁止 JSON / 工具名 / Thought 原文。"
)


class PromptBuilder:
    """设计稿 §3.7。"""

    def build_react_system(
        self,
        *,
        tools: list[str],
        tool_contracts: str,
        skill_body: str,
        query: DispatchQuery,
        context: ContextBundle | None,
        memory_system_block: str = "",
        long_term_memory: str = "",
        transition: TaskTransition | None = None,
    ) -> str:
        import json

        parts = [
            REACT_SYSTEM_PROMPT,
            f"可用工具: {json.dumps(tools, ensure_ascii=False)}",
            tool_contracts,
            skill_body or "",
            _OUTPUT_DISCIPLINE,
        ]
        addon = assemble_react_base_addon(profile=query.profile)
        if addon:
            tier = query.fact_tier or "B"
            parts.append(f"# 本轮路由增强（档位 {tier}）\n{addon}")
        if long_term_memory:
            parts.append(f"# 长期用户记忆（已按当前目标过滤）\n{long_term_memory}")
        if memory_system_block:
            parts.append(memory_system_block)
        if context and context.system_extra:
            parts.append(context.system_extra)
        if transition == TaskTransition.CHITCHAT:
            parts.append("# 本轮判定为自由闲聊：简洁友好即可，勿强行拉起重型任务链路。")
        parts.append(SAFETY_POLICY_PROMPT)
        return "\n\n".join(p for p in parts if p and str(p).strip())

    def build_package(
        self,
        *,
        system: str,
        dialog_messages: list[dict[str, str]],
        tools: list[str],
        temperature: float = 0.2,
        meta: dict[str, Any] | None = None,
    ) -> PromptPackage:
        messages = [{"role": "system", "content": system}]
        messages.extend(dialog_messages or [])
        return PromptPackage(
            system=system,
            messages=messages,
            tools=tools,
            temperature=temperature,
            meta=meta or {},
        )
