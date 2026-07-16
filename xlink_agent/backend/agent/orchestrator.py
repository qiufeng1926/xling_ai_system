"""主 Agent 编排：单智能体 ReAct（Thought → Action → Observation）循环"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, AsyncIterator

from sqlalchemy.orm import Session

from agent.answer import (
    answer_parrots_search_titles,
    enrich_finish_answer,
    expand_selection_followup,
    extract_grounded_entities_from_facts,
    extract_search_hit_cards,
    format_entity_list_answer,
    has_substantive_content_facts,
    is_hollow_answer,
    is_substantive_draft,
    looks_like_internal,
    pick_fetch_url,
    sanitize_public_answer,
    search_only_needs_fetch,
    synthesize_public_answer,
    synthesize_rich_answer,
    tools_shallow_without_body,
    verify_final_answer,
)
from agent.context import (
    TaskContext,
    apply_result_to_context,
    compact_history,
)
from agent.events import sse
from agent.knowledge_fallback import knowledge_fallback_answer, needs_knowledge_fallback
from agent.memory_policy import (
    answer_relevant_to_goal,
    build_dialog_messages,
    expand_dialog_followup,
    filter_long_term_memory_lines,
)
from agent.memory_service import build_memory_context, maybe_update_profile_from_dialog
from agent.model_router import get_chat_model
from agent.run_state import AgentRunState, FinalizePath, RunPhase
from agent.react import (
    REACT_SYSTEM_PROMPT,
    ReactScratchpad,
    build_react_continue_prompt,
    coerce_action_input,
    format_observation,
    parse_react_output,
)
from config.config import agent_max_tool_rounds, confirmation_ttl_sec
from db.models import Confirmation, Message, RunEvent, Skill, UserSkillInstall
from tools.web_tools import render_tool_contracts, validate_and_normalize_args
from tools.runtime import CONFIRM_TOOLS, execute_tool
from utils.logger import get_logger

logger = get_logger("orchestrator")

KNOWN_TOOLS = {
    "web_search",
    "web_fetch",
    "browser_navigate",
    "browser_click",
    "browser_type",
    "browser_extract",
    "browser_screenshot",
    "browser_submit",
    "kb_search",
    "kb_archive_file",
    "http_request",
    "http_request_write",
    "file_list",
    "file_write_markdown",
    "file_write_html",
    "file_write_docx",
    "file_write_xlsx",
    "file_write_pptx",
    "file_write_pdf",
    "file_delete",
}

SYSTEM_PROMPT = REACT_SYSTEM_PROMPT


_FILE_CLAIM_RE = re.compile(
    r"(已生成|生成了|写好了|文档已|文件已|日报\.docx|下载|保存为).{0,40}(文档|文件|docx|xlsx|pdf|pptx|markdown|\.md)|"
    r"(file_write_|日报文档)",
    re.I,
)


def _is_blocked_page(result: dict[str, Any], url: str = "") -> bool:
    """验证码 / 风控页 / HTTP 错误空壳：应换下一条链接，而不是停下来问用户。"""
    if result.get("ok") is False or result.get("error"):
        return True
    status = result.get("status")
    if isinstance(status, int) and status >= 400:
        return True
    blob = " ".join(
        [
            url or "",
            str(result.get("url") or ""),
            str(result.get("title") or ""),
            str(result.get("text") or "")[:1000],
            str(result.get("error") or ""),
        ]
    )
    low = blob.lower()
    ascii_m = ("unhuman", "captcha", "challenge", "/verify", "access denied")
    cn_m = ("安全验证", "人机验证", "访问验证", "请完成验证", "账号异常", "让每一次点击都充满意义")
    return any(m in low for m in ascii_m) or any(m in blob for m in cn_m)


def _claims_file_without_artifact(text: str) -> bool:
    return bool(_FILE_CLAIM_RE.search(text or ""))


def _recover_file_tool(
    raw: str,
    think: str,
    content: str,
    tools: list[str],
    *,
    goal: str = "",
    facts: list[str] | None = None,
) -> dict[str, Any] | None:
    """模型空喊「已生成」时，尝试从本轮输出里找回 file_write_* 调用。"""
    for blob in (raw, think, content):
        parsed = parse_agent_output(blob, tools)
        if parsed.get("action") != "tool":
            continue
        tool = str(parsed.get("tool") or "")
        if tool.startswith("file_write_") and (tool in tools or tool in KNOWN_TOOLS):
            args = parsed.get("args") if isinstance(parsed.get("args"), dict) else {}
            if not args.get("content"):
                parts = [p for p in [goal, *(facts or [])] if p]
                args = {**args, "content": "\n".join(parts)[:4000] or content[:4000]}
            if not args.get("filename"):
                args = {**args, "filename": "日报.docx" if "docx" in tool else "note.md"}
            if not args.get("title"):
                args = {**args, "title": "日报"}
            return {"action": "tool", "tool": tool, "args": args, "think": "补执行写文件"}
    write_tools = [t for t in ("file_write_docx", "file_write_markdown") if t in tools or t in KNOWN_TOOLS]
    if write_tools and _claims_file_without_artifact(f"{think}\n{content}\n{raw}"):
        tool = "file_write_docx" if "file_write_docx" in write_tools else write_tools[0]
        parts = [p for p in [goal, *(facts or [])] if p]
        body = "\n".join(parts).strip() or (content if content and not content.strip().startswith("{") else "（自动补写）")
        filename = "日报.docx" if tool == "file_write_docx" else "日报.md"
        return {
            "action": "tool",
            "tool": tool,
            "args": {"filename": filename, "title": "日报", "content": body[:8000]},
            "think": "用户要文档但模型未真正写文件，自动补写",
        }
    return None


def _active_skills(db: Session, user_id: int) -> list[Skill]:
    installed_ids = [
        r.skill_id
        for r in db.query(UserSkillInstall).filter(UserSkillInstall.user_id == user_id).all()
    ]
    if not installed_ids:
        builtins = db.query(Skill).filter(Skill.scope == "builtin", Skill.enabled.is_(True)).all()
    else:
        builtins = (
            db.query(Skill)
            .filter(Skill.scope == "builtin", Skill.enabled.is_(True), Skill.id.in_(installed_ids))
            .all()
        )
    users = (
        db.query(Skill)
        .filter(Skill.scope == "user", Skill.owner_user_id == user_id, Skill.enabled.is_(True))
        .all()
    )
    return list(builtins) + list(users)


def _merge_tools(skills: list[Skill]) -> tuple[list[str], str]:
    tools: list[str] = []
    bodies: list[str] = []
    for s in skills:
        try:
            t = json.loads(s.tools_json or "[]")
        except Exception:
            t = []
        for name in t:
            if name not in tools:
                tools.append(name)
        bodies.append(f"## Skill: {s.name}\n{s.description}\n{s.body_md}")
    for base in [
        "web_search",
        "web_fetch",
        "kb_search",
        "file_list",
        "file_write_markdown",
        "file_write_html",
        "file_write_docx",
        "file_write_xlsx",
        "file_write_pptx",
        "file_write_pdf",
        "browser_navigate",
        "browser_extract",
        "browser_click",
        "browser_type",
        "browser_screenshot",
        "http_request",
    ]:
        if base not in tools:
            tools.append(base)
    return tools, "\n\n".join(bodies)


def _save_event(db: Session, user_id: int, conversation_id: int, run_id: str, event_type: str, payload: Any) -> None:
    db.add(
        RunEvent(
            conversation_id=conversation_id,
            user_id=user_id,
            run_id=run_id,
            event_type=event_type,
            payload_json=json.dumps(payload, ensure_ascii=False),
        )
    )
    db.commit()


def parse_agent_output(raw: str, allowed_tools: list[str]) -> dict[str, Any]:
    """ReAct 解析 → 兼容旧字段 {action: tool|final, tool, args, think, content}。"""
    parsed = parse_react_output(raw, allowed_tools, KNOWN_TOOLS)
    thought = str(parsed.get("thought") or "")
    action = str(parsed.get("action") or "finish")
    action_input = coerce_action_input(action, parsed.get("action_input"))
    if action == "finish":
        return {"action": "final", "content": str(action_input or ""), "think": thought}
    args = action_input if isinstance(action_input, dict) else {}
    if isinstance(action_input, str) and action_input.strip():
        # 非 dict 入参原样交给运行时校验（如 "深圳天气"）
        return {"action": "tool", "tool": action, "args": action_input, "think": thought}
    return {"action": "tool", "tool": action, "args": args, "think": thought}


def _shrink(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "frame" and isinstance(v, str):
                out[k] = f"<base64:{len(v)}>"
            elif isinstance(v, str) and len(v) > 3000:
                out[k] = v[:3000] + "…"
            else:
                out[k] = _shrink(v)
        return out
    if isinstance(obj, list):
        return [_shrink(x) for x in obj[:50]]
    return obj


def _persist_run_state(
    db: Session,
    user_id: int,
    conversation_id: int,
    run_id: str,
    run_state: AgentRunState,
    *,
    milestone: str = "",
) -> None:
    tag = milestone or run_state.phase.value
    logger.info("run_state[%s] %s | %s", run_id[:8], tag, run_state.attribution_summary())
    _save_event(
        db,
        user_id,
        conversation_id,
        run_id,
        "run.state",
        {"milestone": tag, **run_state.to_dict()},
    )


async def _emit_think(text: str) -> AsyncIterator[str]:
    if not text:
        return
    step = 16
    for i in range(0, len(text), step):
        yield sse("think.delta", {"content": text[i : i + step]})


def _user_facing_text(text: str) -> str:
    """清洗给用户看的最终文案：去 JSON / 协议 / 内部步骤。"""
    return sanitize_public_answer(text)


def _reject_internal_answer(text: str, goal: str = "") -> str:
    t = sanitize_public_answer(text or "")
    if not t or is_hollow_answer(t) or looks_like_internal(t):
        return ""
    if any(
        x in t
        for x in (
            "请输出核实",
            "请输出最终高质量",
            "线索，不是最终答案",
            "待核实草稿",
            "检索材料：",
            "用户目标：",
        )
    ):
        return ""
    return t


async def _finalize_user_answer(
    model,
    task_ctx: TaskContext,
    content: str,
    *,
    round_i: int,
    thought: str = "",
    run_state: Any | None = None,
) -> str:
    """交付：富文本总结为主；绝不把内部草稿/提示词给用户。"""
    goal = task_ctx.goal or ""
    draft = enrich_finish_answer(
        content or "",
        thought=thought,
        facts=task_ctx.facts,
        goal=goal,
    )
    draft = _reject_internal_answer(draft, goal)

    has_materials = bool(extract_search_hit_cards(task_ctx.facts)) or has_substantive_content_facts(
        task_ctx.facts
    )
    fact_n = len(task_ctx.facts)

    def _track(path, text: str) -> str:
        if run_state is not None:
            run_state.record_finalize(path, text, round_i=round_i)
            run_state.snapshot_answer(
                "finalize_ctx",
                text,
                round_i=round_i,
                path=path.value if hasattr(path, "value") else str(path),
                has_materials=has_materials,
                fact_count=fact_n,
            )
        return text

    # finish 已有完整答案：无 Observation 时直接交付，避免总结器改成「没有材料」
    if is_substantive_draft(draft, goal) and not has_materials:
        return _track(FinalizePath.DRAFT_DIRECT_NO_MATERIALS, draft)

    if has_materials:
        rich = await synthesize_rich_answer(
            model,
            goal=goal,
            facts=task_ctx.facts,
            draft=draft,
            thought=thought,
        )
        final = _reject_internal_answer(rich, goal)
        if final and answer_relevant_to_goal(final, goal) and not answer_parrots_search_titles(
            final, task_ctx.facts
        ):
            return _track(FinalizePath.RICH_SYNTHESIS, final)
        if is_substantive_draft(draft, goal):
            return _track(FinalizePath.DRAFT_AFTER_RICH_FAIL, draft)

    elif draft and not is_hollow_answer(draft):
        return _track(FinalizePath.DRAFT_NON_HOLLOW, draft)

    # 无材料且草稿不足：常识兜底
    if not has_materials or needs_knowledge_fallback(goal, task_ctx.facts, max(round_i, 1)):
        if is_substantive_draft(draft, goal):
            return _track(FinalizePath.SUBSTANTIVE_BEFORE_FALLBACK, draft)
        fb = await knowledge_fallback_answer(model, goal)
        final = _reject_internal_answer(fb or "", goal)
        if final:
            return _track(FinalizePath.KNOWLEDGE_FALLBACK, final)

    verified = await verify_final_answer(
        model, goal=goal, facts=task_ctx.facts, draft=draft or "", thought=thought
    )
    final = _reject_internal_answer(verified, goal)
    if final and answer_relevant_to_goal(final, goal):
        return _track(FinalizePath.VERIFIED, final)
    if is_substantive_draft(draft, goal):
        return _track(FinalizePath.SUBSTANTIVE_AFTER_VERIFY, draft)

    entities = extract_grounded_entities_from_facts(task_ctx.facts)
    if entities:
        rich2 = await synthesize_rich_answer(
            model,
            goal=goal,
            facts=task_ctx.facts,
            draft=format_entity_list_answer(goal, entities),
            thought=thought,
        )
        final = _reject_internal_answer(rich2, goal)
        if final:
            return _track(FinalizePath.ENTITY_SYNTHESIS, final)
        return _track(
            FinalizePath.ENTITY_LIST_RAW,
            sanitize_public_answer(format_entity_list_answer(goal, entities)),
        )

    fb = await knowledge_fallback_answer(model, goal)
    return _track(
        FinalizePath.KNOWLEDGE_LAST_RESORT,
        sanitize_public_answer(fb or "请换个更具体的说法再问一次。"),
    )


async def _emit_answer(text: str) -> AsyncIterator[str]:
    text = _user_facing_text(text)
    step = 20
    for i in range(0, len(text), step):
        yield sse("message.delta", {"content": text[i : i + step]})


async def run_chat(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    user_text: str,
) -> AsyncIterator[str]:
    run_id = uuid.uuid4().hex
    maybe_update_profile_from_dialog(db, user_id, user_text)

    db.add(
        Message(
            conversation_id=conversation_id,
            user_id=user_id,
            role="user",
            content=user_text,
        )
    )
    db.commit()

    history = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.id.asc())
        .limit(40)
        .all()
    )
    # 「2」编号续作 / 「你为什么获取不了」类追问：展开为带上下文的目标
    expanded = expand_selection_followup(user_text, history)
    if not expanded:
        expanded = expand_dialog_followup(user_text, history, sanitize_fn=sanitize_public_answer)
    effective_goal = (expanded or user_text).strip()
    if expanded:
        logger.info("followup expanded: %r -> %r", user_text[:40], effective_goal[:160])

    skills = _active_skills(db, user_id)
    tools, skill_body = _merge_tools(skills)
    memory_raw = build_memory_context(db, user_id)
    memory_ctx = filter_long_term_memory_lines(memory_raw, effective_goal)

    # 本轮任务记忆：全新开始，不继承上轮 facts / 浏览器残留页
    task_ctx = TaskContext(
        goal=effective_goal,
        browser_url="about:blank",
    )
    run_state = AgentRunState(run_id=run_id, goal=effective_goal)
    run_state.transition(RunPhase.INIT, reason="task_context_ready")

    system = SYSTEM_PROMPT + f"\n\n可用工具: {json.dumps(tools, ensure_ascii=False)}\n\n"
    system += render_tool_contracts(tools) + "\n\n" + skill_body
    if memory_ctx:
        system += f"\n\n# 长期用户记忆（已按当前目标过滤）\n{memory_ctx}"
    system += (
        "\n\n# 记忆纪律\n"
        "1. 独立新问题与上一轮硬隔离：禁止联想/提及上一轮书名、新闻或结论。\n"
        "2. 仅当用户明确追问/续作（再来三本、为什么获取不了、详细讲《某书》）才使用最近同题上下文。\n"
        "3. finish 必须是用户可读终稿：总起 + 要点；禁止输出「线索/请核实/检索材料」等内部话术。\n"
        "4. 只读搜索/抓取无需用户确认；自行 web_fetch 后总结交付。\n"
    )
    logger.info(
        "======== system prompt preview run=%s len=%s ========\n%s",
        run_id[:8],
        len(system),
        system,
    )

    base_messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    base_messages.extend(
        build_dialog_messages(
            history,
            current_goal=effective_goal,
            sanitize_fn=sanitize_public_answer,
            looks_internal_fn=looks_like_internal,
        )
    )

    model = get_chat_model()
    assistant_parts: list[str] = []
    think_parts: list[str] = []
    file_meta: list[dict[str, Any]] = []
    empty_extract_retries = 0
    scratchpad = ReactScratchpad()

    yield sse("run.started", {"run_id": run_id, "architecture": "react"})
    yield sse("think.open", {"title": "ReAct 推理"})
    if expanded:
        async for chunk in _emit_think(f"识别为编号续作，已展开目标：{effective_goal}\n"):
            yield chunk
            think_parts.append("编号续作展开")
    async for chunk in _emit_think("ReAct：建立任务工作记忆…\n"):
        yield chunk
        think_parts.append("建立任务工作记忆")
    async for chunk in _emit_think(task_ctx.render() + "\n"):
        yield chunk

    for round_i in range(agent_max_tool_rounds):
        run_state.begin_round(round_i)
        # ReAct：每轮 = 读工作记忆 + scratchpad → Thought/Action → Observation
        messages = compact_history(base_messages, limit_pairs=4)
        messages.append(
            {
                "role": "user",
                "content": build_react_continue_prompt(task_ctx.render(), scratchpad),
            }
        )

        raw = await model.chat(messages, temperature=0.2)
        logger.info("react round=%s: %s", round_i, raw[:500])
        parsed = parse_agent_output(raw, tools)
        think = str(parsed.get("think") or "")
        action = parsed.get("action")
        run_state.record_react_parsed(
            round_i=round_i,
            action=str(action or ""),
            tool=str(parsed.get("tool") or ""),
            thought=think,
        )
        if think:
            yield sse("react.thought", {"round": round_i, "thought": think})
            async for chunk in _emit_think(f"Thought: {think}\n"):
                yield chunk
                think_parts.append(think)

        if action == "final":
            content = str(parsed.get("content") or "").strip()
            maybe_tool = parse_agent_output(content, tools) if content else None
            if maybe_tool and maybe_tool.get("action") == "tool" and maybe_tool.get("tool") in tools:
                parsed = maybe_tool
                action = "tool"
            elif (
                not task_ctx.artifacts
                and _claims_file_without_artifact(f"{think}\n{content}\n{raw}")
                and round_i < agent_max_tool_rounds - 1
            ):
                recovered = _recover_file_tool(
                    raw,
                    think,
                    content,
                    tools,
                    goal=task_ctx.goal,
                    facts=task_ctx.facts,
                )
                if recovered:
                    run_state.intercept("file_claim_recover", round_i=round_i)
                    async for chunk in _emit_think("检测到空喊「已生成文件」，改为实际调用写文件工具…\n"):
                        yield chunk
                    parsed = recovered
                    action = "tool"
                else:
                    async for chunk in _emit_think(
                        "用户需要生成文档，但尚未调用 file_write_*。请输出 tool 调用，不要只说已生成。\n"
                    ):
                        yield chunk
                    task_ctx.add_step("拦截未写文件的 final")
                    continue
            else:
                # 过早 finish 且本轮无任何有效事实：概念题可直接答；其它引导 web_search
                if (
                    not task_ctx.facts
                    and round_i < agent_max_tool_rounds - 1
                    and not any(k in (task_ctx.goal or "") for k in ("写", "生成文档", "docx", "日报"))
                    and not re.match(r"^\s*(什么是|什么叫|何为|谁是)", task_ctx.goal or "")
                ):
                    run_state.intercept("premature_finish_auto_search", round_i=round_i)
                    async for chunk in _emit_think("尚未拿到有效 Observation，先 web_search 再决策…\n"):
                        yield chunk
                    parsed = {
                        "action": "tool",
                        "tool": "web_search",
                        "args": {"query": task_ctx.goal},
                        "think": "自动补搜索",
                    }
                    action = "tool"
                else:
                    if not content:
                        content = ""
                    # 空壳 finish：若 thought/搜索事实已能补全则直接交付；
                    # 有搜索结果但未抓正文：禁止让用户选编号，自动 web_fetch
                    enriched_preview = enrich_finish_answer(
                        content,
                        thought=think,
                        facts=task_ctx.facts,
                        goal=task_ctx.goal or "",
                    )
                    fetched_already = any(
                        s.action in {"web_fetch", "http_request", "browser_extract", "browser_navigate"}
                        for s in scratchpad.steps
                    )
                    next_url = pick_fetch_url(task_ctx.facts, skip=set(task_ctx.failed_urls))
                    must_fetch = (
                        bool(next_url)
                        and not fetched_already
                        and round_i < agent_max_tool_rounds - 1
                        and (
                            search_only_needs_fetch(task_ctx.facts, fetched_already=fetched_already)
                            or (
                                is_hollow_answer(content)
                                and is_hollow_answer(enriched_preview)
                            )
                        )
                    )
                    if must_fetch and next_url:
                        run_state.intercept("auto_web_fetch", round_i=round_i, url=next_url[:120])
                        async for chunk in _emit_think(
                            f"只读任务不需用户选择，自动 web_fetch: {next_url[:100]}\n"
                        ):
                            yield chunk
                        parsed = {
                            "action": "tool",
                            "tool": "web_fetch",
                            "args": {"url": next_url},
                            "think": "搜索后自动抓取内容页",
                        }
                        action = "tool"
                    else:
                        run_state.react_finish_draft = content
                        run_state.snapshot_answer(
                            "react_finish",
                            content,
                            round_i=round_i,
                            fact_count=len(task_ctx.facts),
                        )
                        content = await _finalize_user_answer(
                            model, task_ctx, content, round_i=round_i, thought=think, run_state=run_state
                        )
                        # 去掉残留的「告诉我编号」类话术
                        content = re.sub(
                            r"\n*如需某一条的详细内容[^\n]*\n?",
                            "\n",
                            content,
                        ).strip()
                        scratchpad.add_thought_action(think, "finish", content, round_i)
                        scratchpad.set_observation("（已向用户交付最终答案）")
                        run_state.record_delivered(content)
                        yield sse(
                            "react.finish",
                            {"round": round_i, "thought": think, "content": content[:500]},
                        )
                        async for chunk in _emit_answer(content):
                            yield chunk
                        assistant_parts = [content]
                        break

        if action == "tool":
            tool = str(parsed.get("tool") or "")
            args = parsed.get("args") if isinstance(parsed.get("args"), (dict, str)) else {}

            # 入参校验/归一化（通用契约，不做业务强制改写）
            norm, verr = validate_and_normalize_args(tool, args)
            if verr:
                tip = f"工具参数无效: {verr}"
                scratchpad.add_thought_action(think, tool, args, round_i)
                scratchpad.set_observation(tip)
                yield sse("react.action", {"round": round_i, "tool": tool, "args": args, "thought": think})
                yield sse("react.observation", {"round": round_i, "observation": tip, "tool": tool})
                async for chunk in _emit_think(f"Observation: {tip}\n"):
                    yield chunk
                continue
            args = norm or {}

            # 相同 web_search 须在记入 scratchpad 之前判断，否则会把自己算成「已搜过」而永远不执行
            if tool == "web_search":
                q = str((args or {}).get("query") or "").strip()
                prior_q = [
                    str((s.action_input or {}).get("query") or "").strip()
                    if isinstance(s.action_input, dict)
                    else ""
                    for s in scratchpad.steps
                    if s.action == "web_search"
                ]
                if q and q in prior_q:
                    run_state.intercept("duplicate_web_search", round_i=round_i, query=q[:80])
                    next_u = pick_fetch_url(task_ctx.facts, skip=set(task_ctx.failed_urls))
                    if next_u:
                        async for chunk in _emit_think(
                            f"已搜索过「{q[:40]}」，改为 web_fetch: {next_u[:100]}\n"
                        ):
                            yield chunk
                        tool = "web_fetch"
                        args = {"url": next_u}
                    elif task_ctx.facts:
                        tip = "相同搜索词已执行过，请基于已有 Observation finish，勿重复搜索。"
                        scratchpad.add_thought_action(think, tool, args, round_i)
                        scratchpad.set_observation(tip)
                        yield sse("react.observation", {"round": round_i, "observation": tip, "tool": tool})
                        async for chunk in _emit_think(f"Observation: {tip}\n"):
                            yield chunk
                        continue
                    # 无 facts 却重复搜：换 query 再试一次，不要空转
                    elif round_i < agent_max_tool_rounds - 1:
                        alt_q = task_ctx.goal or q
                        if alt_q != q:
                            async for chunk in _emit_think(f"搜索无结果，改用目标原文再搜: {alt_q[:60]}\n"):
                                yield chunk
                            args = {"query": alt_q}

            scratchpad.add_thought_action(think, tool, args, round_i)
            yield sse(
                "react.action",
                {"round": round_i, "tool": tool, "args": args, "thought": think},
            )
            if tool not in tools and tool not in CONFIRM_TOOLS:
                tip = f"工具不在白名单: {tool}。请改用: {', '.join(tools[:12])}"
                scratchpad.set_observation(tip)
                yield sse("react.observation", {"round": round_i, "observation": tip})
                async for chunk in _emit_think(f"Observation: {tip}\n"):
                    yield chunk
                task_ctx.add_step(tip)
                continue

            # 禁止对已失败 URL / 相同参数死循环重试
            nav_url = str(args.get("url") or "")
            if tool == "browser_navigate" and nav_url and nav_url in task_ctx.failed_urls:
                async for chunk in _emit_think(
                    f"URL 已失败过，跳过重复 navigate，改用 http_request 抓取: {nav_url}\n"
                ):
                    yield chunk
                tool = "http_request"
                args = {"method": "GET", "url": nav_url}
            elif task_ctx.already_failed(tool, args, limit=1):
                tip = f"检测到重复失败调用 {tool}，已拦截。请换策略或直接总结已有信息。"
                scratchpad.set_observation(tip)
                yield sse("react.observation", {"round": round_i, "observation": tip, "tool": tool})
                async for chunk in _emit_think(f"Observation: {tip}\n"):
                    yield chunk
                task_ctx.add_step(f"拦截重复失败: {tool} {nav_url}")
                continue

            # 空白页上的 extract/点击：不要瞎跳新闻站；改为对本目标做 web_search
            if tool in {"browser_extract", "browser_click", "browser_type", "browser_screenshot"} and (
                task_ctx.browser_url in {"", "about:blank"}
            ):
                async for chunk in _emit_think(
                    "浏览器尚未打开有效页面，改用 web_search 获取信息…\n"
                ):
                    yield chunk
                tool = "web_search"
                args = {"query": task_ctx.goal}
                norm2, verr2 = validate_and_normalize_args(tool, args)
                if verr2:
                    tip = f"工具参数无效: {verr2}"
                    scratchpad.set_observation(tip)
                    yield sse("react.observation", {"round": round_i, "observation": tip, "tool": tool})
                    async for chunk in _emit_think(f"Observation: {tip}\n"):
                        yield chunk
                    continue
                args = norm2 or args

            # 只读打开优先 web_fetch，少踩浏览器验证码
            if tool == "browser_navigate" and str(args.get("url") or "").startswith("http"):
                g = task_ctx.goal or ""
                if not any(k in g for k in ("登录", "填表", "提交表单", "点按钮", "点击")):
                    async for chunk in _emit_think(
                        f"只读任务改用 web_fetch，避免浏览器验证码: {str(args.get('url'))[:80]}\n"
                    ):
                        yield chunk
                    tool = "web_fetch"

            tip = f"Action: {tool} {json.dumps(args, ensure_ascii=False)}"
            async for chunk in _emit_think(tip + "\n"):
                yield chunk

            yield sse("tool.started", {"tool": tool, "args": args, "round": round_i})
            _save_event(db, user_id, conversation_id, run_id, "tool.started", {"tool": tool, "args": args})
            run_state.record_tool_start(tool, args)

            if tool in CONFIRM_TOOLS:
                conf = Confirmation(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    run_id=run_id,
                    action_type=tool,
                    payload_json=json.dumps({"tool": tool, "args": args}, ensure_ascii=False),
                    status="pending",
                )
                db.add(conf)
                db.commit()
                db.refresh(conf)
                yield sse(
                    "confirmation.required",
                    {
                        "id": conf.id,
                        "action_type": tool,
                        "args": args,
                        "expires_in": confirmation_ttl_sec,
                    },
                )
                notice = f"需要你确认操作：`{tool}`。请在确认条中同意或拒绝后继续。"
                async for chunk in _emit_answer(notice):
                    yield chunk
                assistant_parts = [notice]
                run_state.transition(RunPhase.AWAITING_CONFIRM, round_i=round_i, reason=tool)
                _persist_run_state(db, user_id, conversation_id, run_id, run_state, milestone="awaiting_confirm")
                break

            try:
                result = await execute_tool(
                    tool,
                    args,
                    db=db,
                    user_id=user_id,
                    conversation_id=conversation_id,
                )
            except Exception as exc:
                logger.warning("tool failed: %s %s", tool, exc)
                result = {"error": str(exc)}
                if tool == "browser_navigate" and args.get("url"):
                    result["failed_url"] = args["url"]
                    result["url"] = args["url"]

            if not isinstance(result, dict):
                result = {"error": "bad result"}

            # navigate 失败后自动尝试 http 兜底一次
            if tool == "browser_navigate" and result.get("error") and args.get("url"):
                fail_url = str(args.get("url"))
                apply_result_to_context(task_ctx, tool, result, args=args)
                yield sse("tool.finished", {"tool": tool, "result": _shrink(result)})
                async for chunk in _emit_think(f"浏览器打不开，改用 http_request: {fail_url}\n"):
                    yield chunk
                tool = "http_request"
                args = {"method": "GET", "url": fail_url}
                yield sse("tool.started", {"tool": tool, "args": args, "round": round_i})
                try:
                    result = await execute_tool(
                        tool,
                        args,
                        db=db,
                        user_id=user_id,
                        conversation_id=conversation_id,
                    )
                except Exception as exc:
                    logger.warning("http_request fallback failed: %s", exc)
                    result = {"error": str(exc)}

            apply_result_to_context(
                task_ctx,
                tool,
                result if isinstance(result, dict) else {"error": "bad result"},
                args=args,
            )

            # 验证码/风控：立刻换下一条内容链接 web_fetch（不问用户选编号）
            cur_url = str((args or {}).get("url") or (result.get("url") if isinstance(result, dict) else "") or "")
            if (
                tool in {"web_fetch", "browser_navigate", "http_request", "browser_extract"}
                and isinstance(result, dict)
                and _is_blocked_page(result, cur_url)
                and round_i < agent_max_tool_rounds - 1
            ):
                if cur_url:
                    task_ctx.mark_failed_url(cur_url)
                next_u = pick_fetch_url(task_ctx.facts, skip=set(task_ctx.failed_urls))
                tip_block = f"命中验证码/风控页，跳过: {cur_url[:100]}"
                async for chunk in _emit_think(tip_block + "\n"):
                    yield chunk
                scratchpad.set_observation(tip_block)
                if next_u:
                    async for chunk in _emit_think(f"自动改抓下一条: {next_u[:100]}\n"):
                        yield chunk
                    tool = "web_fetch"
                    args = {"url": next_u}
                    yield sse("tool.started", {"tool": tool, "args": args, "round": round_i})
                    try:
                        result = await execute_tool(
                            tool,
                            args,
                            db=db,
                            user_id=user_id,
                            conversation_id=conversation_id,
                        )
                    except Exception as exc:
                        result = {"error": str(exc)}
                    if not isinstance(result, dict):
                        result = {"error": "bad result"}
                    apply_result_to_context(task_ctx, tool, result, args=args)
                    if _is_blocked_page(result, next_u):
                        task_ctx.mark_failed_url(next_u)

            if isinstance(result, dict) and result.get("frame"):
                yield sse("browser.frame", {"url": result.get("url"), "frame": result["frame"]})
            if isinstance(result, dict) and result.get("file_id"):
                item = {"file_id": result["file_id"], "name": result.get("name")}
                file_meta.append(item)
                yield sse("file.ready", item)

            obs = format_observation(tool, result)
            scratchpad.set_observation(obs)
            run_state.record_tool_done(
                tool,
                bool(task_ctx.last_ok),
                summary=obs[:400],
            )
            yield sse("react.observation", {"round": round_i, "observation": obs, "tool": tool})
            async for chunk in _emit_think(f"Observation: {obs}\n"):
                yield chunk

            yield sse("tool.finished", {"tool": tool, "result": _shrink(result)})
            _save_event(
                db,
                user_id,
                conversation_id,
                run_id,
                "tool.finished",
                {"tool": tool, "result": _shrink(result)},
            )

            if tool == "browser_extract" and not task_ctx.last_ok:
                empty_extract_retries += 1
                if empty_extract_retries >= 2 and task_ctx.browser_url not in {"", "about:blank"}:
                    # 第二次抽取失败：改为无 selector 抽 body
                    async for chunk in _emit_think("选择器可能无效，改为抽取整页正文…\n"):
                        yield chunk
                    body_result = await execute_tool(
                        "browser_extract",
                        {},
                        db=db,
                        user_id=user_id,
                        conversation_id=conversation_id,
                    )
                    apply_result_to_context(task_ctx, "browser_extract", body_result)
                    if isinstance(body_result, dict) and body_result.get("frame"):
                        yield sse(
                            "browser.frame",
                            {"url": body_result.get("url"), "frame": body_result["frame"]},
                        )

            async for chunk in _emit_think("ReAct：准备下一步 Thought…\n"):
                yield chunk

            # 多轮仍无与目标相关实质事实：通用常识兜底（不限业务场景）
            if needs_knowledge_fallback(task_ctx.goal, task_ctx.facts, round_i + 1):
                async for chunk in _emit_think(
                    "工具尚未形成足够 Observation，改用常识直接回答用户…\n"
                ):
                    yield chunk
                content = await _finalize_user_answer(
                    model, task_ctx, "", round_i=round_i + 1, run_state=run_state
                )
                scratchpad.add_thought_action("工具结果不足，知识兜底", "finish", content, round_i)
                scratchpad.set_observation("（知识兜底）")
                run_state.record_delivered(content)
                yield sse("react.finish", {"round": round_i, "thought": "knowledge_fallback", "content": content[:500]})
                async for chunk in _emit_answer(content):
                    yield chunk
                assistant_parts = [content]
                break
            continue

        content = await _finalize_user_answer(
            model, task_ctx, str(parsed.get("content") or raw), round_i=round_i, run_state=run_state
        )
        run_state.record_delivered(content)
        async for chunk in _emit_answer(content):
            yield chunk
        assistant_parts = [content]
        break
    else:
        content = await _finalize_user_answer(
            model, task_ctx, "", round_i=agent_max_tool_rounds, run_state=run_state
        )
        run_state.record_delivered(content)
        async for chunk in _emit_answer(content):
            yield chunk
        assistant_parts = [content]

    yield sse("think.close", {})
    final_text = _user_facing_text("".join(assistant_parts).strip()) or ""
    if not final_text or looks_like_internal(final_text) or not answer_relevant_to_goal(
        final_text, task_ctx.goal or ""
    ):
        final_text = await _finalize_user_answer(
            model, task_ctx, final_text, round_i=agent_max_tool_rounds, run_state=run_state
        )
    run_state.record_delivered(final_text)
    run_state.complete()
    _persist_run_state(db, user_id, conversation_id, run_id, run_state, milestone="complete")
    if task_ctx.artifacts and all(a not in final_text for a in task_ctx.artifacts):
        final_text = (
            final_text.rstrip()
            + "\n\n"
            + f"文件 {'、'.join(task_ctx.artifacts)} 已准备好，可点击下方下载。"
        )
    db.add(
        Message(
            conversation_id=conversation_id,
            user_id=user_id,
            role="assistant",
            content=final_text,
            metadata_json=json.dumps(
                {
                    "run_id": run_id,
                    "architecture": "react",
                    "think": "".join(think_parts)[:4000],
                    "react_steps": [
                        {
                            "thought": s.thought[:500],
                            "action": s.action,
                            "observation": (s.observation or "")[:1500],
                            "round": s.round_i,
                        }
                        for s in scratchpad.steps[-12:]
                    ],
                    "files": file_meta,
                    "task_context": {
                        "goal": task_ctx.goal,
                        "browser_url": task_ctx.browser_url,
                        "facts": task_ctx.facts[-10:],
                        "artifacts": task_ctx.artifacts,
                    },
                    "run_state": run_state.to_dict(),
                },
                ensure_ascii=False,
            ),
        )
    )
    db.commit()
    yield sse("done", {"run_id": run_id, "finalize_path": run_state.finalize_path})


async def resume_after_confirmation(
    db: Session,
    *,
    user_id: int,
    confirmation_id: int,
    approved: bool,
) -> dict:
    conf = db.get(Confirmation, confirmation_id)
    if not conf or conf.user_id != user_id:
        return {"ok": False, "error": "确认单不存在"}
    if conf.status != "pending":
        return {"ok": False, "error": "确认单已处理"}
    if conf.created_at and datetime.utcnow() - conf.created_at > timedelta(seconds=confirmation_ttl_sec):
        conf.status = "expired"
        conf.resolved_at = datetime.utcnow()
        db.commit()
        return {"ok": False, "error": "确认已过期"}

    conf.status = "approved" if approved else "rejected"
    conf.resolved_at = datetime.utcnow()
    db.commit()

    if not approved:
        return {"ok": True, "status": "rejected"}

    payload = json.loads(conf.payload_json or "{}")
    tool = payload.get("tool") or conf.action_type
    args = payload.get("args") or {}
    try:
        result = await execute_tool(
            tool,
            args,
            db=db,
            user_id=user_id,
            conversation_id=conf.conversation_id,
        )
        return {"ok": True, "status": "approved", "result": _shrink(result)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
