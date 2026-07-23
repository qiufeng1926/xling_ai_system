"""主 Agent 编排：单智能体 ReAct（Thought → Action → Observation）循环"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, AsyncIterator

from sqlalchemy.orm import Session

from agent.answer import (
    answer_depth_score,
    answer_keeps_draft_titles,
    answer_parrots_search_titles,
    asks_user_to_pick_number,
    build_citations,
    enrich_finish_answer,
    ensure_knowledge_disclaimer,
    expand_selection_followup,
    extract_grounded_entities_from_facts,
    extract_search_hit_cards,
    format_entity_list_answer,
    format_title_marks_as_list,
    has_substantive_content_facts,
    honest_grounded_list_answer,
    is_count_list_goal,
    is_count_shortfall,
    is_honest_shortfall_answer,
    is_hollow_answer,
    is_poorly_grounded,
    is_substantive_draft,
    is_thin_list_draft,
    is_title_only_list_answer,
    looks_like_internal,
    materials_usable_for_goal,
    pick_fetch_url,
    rescue_count_list_answer,
    sanitize_hallucinated_list_answer,
    sanitize_public_answer,
    search_only_needs_fetch,
    strip_pick_number_prompts,
    synthesize_public_answer,
    synthesize_rich_answer,
    tools_shallow_without_body,
    verify_final_answer,
)
from agent.checkpoint import (
    build_confirm_checkpoint,
    parse_checkpoint,
    restore_scratchpad,
    restore_task_context,
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
from agent.model_router import LLMCallError, get_chat_model
from agent.run_state import AgentRunState, FinalizePath, RunPhase
from agent.react import (
    REACT_SYSTEM_PROMPT,
    ReactScratchpad,
    build_react_continue_prompt,
    coerce_action_input,
    format_observation,
    parse_react_output,
)
from agent.research_policy import (
    alt_search_queries,
    can_finish_research,
    count_search_steps,
    has_search_hit_facts,
    is_near_duplicate_search_query,
    next_research_tool,
    prior_search_queries,
)
from agent.delivery_gate import get_default_delivery_gate
from agent.safety import (
    SAFETY_POLICY_PROMPT,
    SAFETY_REFUSAL,
    answer_contains_prohibited_detail,
    enforce_safety_answer,
    is_disallowed_request,
    is_safety_refusal,
)
from agent.entity_match import (
    expand_goal_with_entities,
    merge_entity_hits_into_task_artifacts,
)
from agent.memory_pipeline import assemble_memory_context
from agent.session_memory import maybe_compact_conversation
from agent.task_binding import (
    expand_goal_with_task,
    required_file_write_tool,
    resolve_task_binding,
    update_task_after_turn,
)
from agent.preprocess import build_request_profile
from agent.prompts.assembler import assemble_react_base_addon
from agent.inference.param_policy import params_for_profile
from agent.delivery.types import FactTier
from agent.trajectory import (
    action_step,
    confirm_tool_label,
    finish_step,
    intercept_step,
    observation_step,
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
    "run_code",
    "memory_recall",
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


def _fill_file_write_args(
    tool: str,
    args: dict[str, Any] | str,
    *,
    goal: str = "",
    think: str = "",
    facts: list[str] | None = None,
) -> dict[str, Any]:
    """写文件前补全正文：模型常把分析写在 Thought，content 却为空。"""
    from tools.web_tools import _pick_write_content

    if not isinstance(args, dict):
        args = {}
    else:
        args = dict(args)
    existing = _pick_write_content(args)
    if len(existing.strip()) >= 40:
        args["content"] = existing
        return args

    parts: list[str] = []
    # 优先用 Thought 里的长文（模型常把正文写在 thought）
    th = (think or "").strip()
    if len(th) >= 80 and not th.startswith("{"):
        parts.append(th)
    # 再用本轮 facts / 材料
    from agent.answer import materials_blob_for_synthesis

    blob = materials_blob_for_synthesis(facts or [], goal=goal or "")
    if blob and len(blob) >= 40:
        parts.append(blob)
    elif facts:
        parts.extend([f for f in facts if len(f) >= 40][-6:])
    if goal and goal not in "\n".join(parts):
        parts.insert(0, f"# {goal}")
    body = "\n\n".join(p for p in parts if p).strip()
    if len(body) >= 40:
        args["content"] = body[:12000]
        if not args.get("title"):
            args["title"] = (goal or "分析报告")[:40]
        if not args.get("filename"):
            suffix = ".docx" if "docx" in tool else (".md" if "markdown" in tool else ".txt")
            safe = re.sub(r'[\\/:*?"<>|]+', "_", (goal or "document")[:24]) or "document"
            args["filename"] = f"{safe}{suffix}"
    return args


async def _ensure_file_write_content(
    model,
    tool: str,
    args: dict[str, Any] | str,
    *,
    goal: str = "",
    think: str = "",
    facts: list[str] | None = None,
) -> dict[str, Any]:
    """写文件前确保正文充实：启发式补全不足时用合成器扩写。"""
    filled = _fill_file_write_args(tool, args, goal=goal, think=think, facts=facts)
    content = str(filled.get("content") or "").strip()
    if len(content) >= 80 and not is_thin_list_draft(content):
        return filled
    seed = content or think or goal
    try:
        rich = await synthesize_rich_answer(
            model,
            goal=goal or "文档",
            facts=facts or [],
            draft=seed,
            thought=think,
            force_expand=True,
        )
    except Exception as exc:
        logger.warning("file_write synthesize failed: %s", exc)
        rich = ""
    rich = (rich or "").strip()
    if len(rich) >= 40:
        filled["content"] = rich[:12000]
        if not filled.get("title"):
            filled["title"] = (goal or "分析报告")[:40]
        if not filled.get("filename"):
            suffix = ".docx" if "docx" in tool else (".md" if "markdown" in tool else ".txt")
            safe = re.sub(r'[\\/:*?"<>|]+', "_", (goal or "document")[:24]) or "document"
            filled["filename"] = f"{safe}{suffix}"
    return filled


def _claims_file_without_artifact(text: str) -> bool:
    return bool(_FILE_CLAIM_RE.search(text or ""))


def _skip_premature_auto_search(goal: str) -> bool:
    """纯写作类（无调研意图）可不强制先搜；含调研/报告则必须搜。"""
    g = goal or ""
    if any(
        k in g
        for k in (
            "调研",
            "检索",
            "搜索",
            "查一下",
            "市场情况",
            "研究报告",
            "详细报告",
            "联网",
        )
    ):
        return False
    return any(k in g for k in ("写日报", "写周报", "写邮件", "起草", "润色"))


def _force_file_write_action(
    *,
    tool: str,
    goal: str,
    think: str = "",
    content: str = "",
    facts: list[str] | None = None,
) -> dict[str, Any]:
    """约束要求落盘时，用已有草稿/材料拼出 file_write_* 调用。"""
    suffix = {
        "file_write_docx": ".docx",
        "file_write_markdown": ".md",
        "file_write_xlsx": ".xlsx",
        "file_write_pptx": ".pptx",
        "file_write_pdf": ".pdf",
        "file_write_html": ".html",
    }.get(tool, ".docx")
    safe = re.sub(r'[\\/:*?"<>|]+', "_", (goal or "document").split("\n", 1)[0][:24]) or "document"
    args = _fill_file_write_args(
        tool,
        {
            "filename": f"{safe}{suffix}",
            "title": (goal or "报告").split("\n", 1)[0][:40],
        },
        goal=goal,
        think=think or content,
        facts=facts,
    )
    if len(str(args.get("content") or "").strip()) < 40:
        body = (content if content and not content.strip().startswith("{") else "") or "\n".join(
            [goal, *(facts or [])]
        )
        args["content"] = (body or "（自动补写正文）")[:8000]
    return {
        "action": "tool",
        "tool": tool,
        "args": args,
        "think": "用户约束要求输出文档，先落盘再交付",
    }


def _recover_file_tool(
    raw: str,
    think: str,
    content: str,
    tools: list[str],
    *,
    goal: str = "",
    facts: list[str] | None = None,
    preferred_tool: str | None = None,
) -> dict[str, Any] | None:
    """模型空喊「已生成」时，尝试从本轮输出里找回 file_write_* 调用。"""
    for blob in (raw, think, content):
        parsed = parse_agent_output(blob, tools)
        if parsed.get("action") != "tool":
            continue
        tool = str(parsed.get("tool") or "")
        if tool.startswith("file_write_") and (tool in tools or tool in KNOWN_TOOLS):
            args = parsed.get("args") if isinstance(parsed.get("args"), dict) else {}
            args = _fill_file_write_args(tool, args, goal=goal, think=think, facts=facts)
            if not str(args.get("content") or "").strip():
                parts = [p for p in [goal, content, *(facts or [])] if p]
                args = {**args, "content": "\n".join(parts)[:8000]}
            if not args.get("filename"):
                args = {**args, "filename": "报告.docx" if "docx" in tool else "note.md"}
            if not args.get("title"):
                args = {**args, "title": (goal or "报告")[:40]}
            return {"action": "tool", "tool": tool, "args": args, "think": "补执行写文件"}
    write_tools: list[str] = []
    for t in (
        preferred_tool,
        "file_write_docx",
        "file_write_markdown",
        "file_write_xlsx",
        "file_write_pptx",
        "file_write_pdf",
    ):
        if t and (t in tools or t in KNOWN_TOOLS) and t not in write_tools:
            write_tools.append(t)
    if write_tools and (
        preferred_tool
        or _claims_file_without_artifact(f"{think}\n{content}\n{raw}")
    ):
        tool = write_tools[0]
        return _force_file_write_action(
            tool=tool, goal=goal, think=think, content=content, facts=facts
        )
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
        "run_code",
        "memory_recall",
    ]:
        if base not in tools:
            tools.append(base)
    # Open Library 默认关闭：不暴露给模型；技能里若带了也剔除
    try:
        from config import config as cfg

        ol_on = bool(getattr(cfg, "openlibrary_enabled", False))
    except Exception:
        ol_on = False
    if ol_on:
        if "openlibrary_lookup" not in tools:
            tools.append("openlibrary_lookup")
    else:
        tools = [t for t in tools if t != "openlibrary_lookup"]
    return tools, "\n\n".join(bodies)


async def _compact_session_after_turn(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    task_id: str = "",
) -> None:
    """轮次落库后：溢出轮次写成可逆结构化摘要，并写入向量索引。"""
    try:
        hist = (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.id.asc())
            .limit(80)
            .all()
        )
        created = maybe_compact_conversation(
            db,
            user_id=user_id,
            conversation_id=conversation_id,
            history=hist,
            task_id=task_id or "",
        )
        if created:
            from agent.vector_memory import index_conversation_summaries

            await index_conversation_summaries(created)
    except Exception:
        logger.exception(
            "session compact failed conv=%s uid=%s", conversation_id, user_id
        )


async def _maybe_index_tool_observation(
    *,
    user_id: int,
    conversation_id: int,
    task_id: str,
    tool: str,
    result: dict[str, Any],
    run_id: str = "",
) -> None:
    """成功工具 Observation 写入短期向量分块（方案细粒度）。"""
    if not isinstance(result, dict) or result.get("error"):
        return
    # 跳过过重/无信息结果
    if tool in {"browser_screenshot", "memory_recall"}:
        return
    try:
        from agent.vector_memory import index_tool_step

        blob = json.dumps(result, ensure_ascii=False)[:1500]
        if len(blob) < 12:
            return
        await index_tool_step(
            user_id=user_id,
            conversation_id=conversation_id,
            task_id=task_id or "",
            tool=tool,
            observation=blob,
            run_id=run_id,
        )
    except Exception:
        logger.exception("tool_step index failed tool=%s", tool)


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


def _build_assistant_metadata(
    *,
    run_id: str,
    think_parts: list[str],
    scratchpad: ReactScratchpad,
    trajectory_log: list[dict[str, Any]],
    task_ctx: TaskContext,
    run_state: AgentRunState,
    file_meta: list[dict[str, Any]] | None = None,
    citations: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """压缩消息元数据，避免 MySQL TEXT/超大 JSON 写入失败。"""
    # run_state 精简：不要塞满 transitions 明细
    rs = run_state.to_dict()
    rs.pop("transitions", None)
    snaps = rs.get("answer_snapshots") or []
    rs["answer_snapshots"] = snaps[-6:]

    meta: dict[str, Any] = {
        "run_id": run_id,
        "architecture": "react",
        "think": "".join(think_parts)[:2000],
        "react_steps": [
            {
                "thought": (s.thought or "")[:240],
                "action": s.action,
                "observation": (s.observation or "")[:400],
                "round": s.round_i,
            }
            for s in scratchpad.steps[-10:]
        ],
        "trajectory": [
            {
                "round": t.get("round"),
                "kind": t.get("kind"),
                "title": t.get("title"),
                "detail": str(t.get("detail") or "")[:160],
                "status": t.get("status"),
                "reason": str(t.get("reason") or "")[:120],
                "tool": t.get("tool"),
            }
            for t in (trajectory_log or [])[-24:]
            if isinstance(t, dict)
        ],
        "citations": (citations or [])[:8],
        "files": file_meta or [],
        "task_context": {
            "goal": (task_ctx.goal or "")[:300],
            "browser_url": (task_ctx.browser_url or "")[:300],
            "facts": [f[:240] for f in task_ctx.facts[-8:]],
            "artifacts": list(task_ctx.artifacts)[:20],
            "task_id": task_ctx.task_id,
            "task_bind_mode": task_ctx.task_bind_mode,
        },
        "run_state": rs,
    }
    if extra:
        meta.update(extra)
    raw = json.dumps(meta, ensure_ascii=False)
    # 硬上限：即使 LONGTEXT 也控制体积，防极端轮次
    if len(raw) > 120_000:
        meta["think"] = (meta.get("think") or "")[:800]
        meta["react_steps"] = meta["react_steps"][-6:]
        meta["trajectory"] = meta["trajectory"][-12:]
        meta["task_context"]["facts"] = meta["task_context"]["facts"][-4:]
        raw = json.dumps(meta, ensure_ascii=False)
    return raw


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


async def _answer_after_llm_failure(
    model,
    task_ctx: TaskContext,
    *,
    round_i: int,
    run_state: Any | None = None,
) -> str:
    """模型重试耗尽后：尽量用已有材料收束，避免 ASGI/SSE 直接崩掉。"""
    from agent.research_policy import is_deep_research_goal

    # 深度调研且几乎无材料：禁止用常识编造「详细报告」交差
    if is_deep_research_goal(task_ctx.goal or "") and not (task_ctx.facts or []):
        return (
            "模型服务暂时超时，且本轮尚未完成检索，无法交付可靠的调研结论。"
            "请再发一次同样的请求，我会重新联网调研后再答复。"
        )
    try:
        text = await _finalize_user_answer(
            model, task_ctx, "", round_i=round_i, thought="", run_state=run_state
        )
        text = _user_facing_text(text or "")
        if text and not looks_like_internal(text):
            return text
    except Exception as exc:  # noqa: BLE001
        logger.warning("finalize after llm failure also failed: %s", exc)
    offline = synthesize_public_answer(task_ctx)
    if offline:
        return enforce_safety_answer(goal=task_ctx.goal or "", answer=offline)
    return (
        "模型服务暂时不稳定（网络或 SSL 中断），请稍后再试。"
        "若刚才已搜到结果，也可以换个说法继续问，我会优先基于已有材料作答。"
    )


async def _finalize_user_answer(
    model,
    task_ctx: TaskContext,
    content: str,
    *,
    round_i: int,
    thought: str = "",
    run_state: Any | None = None,
) -> str:
    """交付流水线入口：预处理 → 综合 → 格式重试 → 门控 → 输出决策。"""
    from agent.delivery.pipeline import run_delivery_pipeline

    return await run_delivery_pipeline(
        model,
        task_ctx,
        content,
        round_i=round_i,
        thought=thought,
        run_state=run_state,
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

    # —— 调度层：会话 / 预处理 / 检索 / 上下文 / 任务状态 / 工具 / 组装 ——
    from agent.dispatch import DispatchRequest, get_dispatch_layer

    def _merge_tools_for_user(sess: Session, uid: int) -> tuple[list[str], str]:
        return _merge_tools(_active_skills(sess, uid))

    dispatch = get_dispatch_layer()
    turn = await dispatch.prepare_turn(
        db,
        DispatchRequest(
            user_id=user_id,
            session_id=conversation_id,
            message=user_text,
            run_id=run_id,
        ),
        merge_tools_fn=_merge_tools_for_user,
        sanitize_fn=sanitize_public_answer,
        looks_internal_fn=looks_like_internal,
    )
    active_task = turn.active_task
    effective_goal = turn.effective_goal
    memory_asm = turn.memory_asm
    entity_result = memory_asm.entity_result
    summary_views = memory_asm.summary_views
    vector_hit_count = int(memory_asm.debug.get("vector_hits") or 0)
    tools = turn.tools
    req_profile = turn.request_profile
    react_params = params_for_profile(req_profile, phase="react")
    expanded = turn.query.is_followup

    task_ctx = TaskContext(
        goal=effective_goal,
        browser_url="about:blank",
        task_id=active_task.task_id,
        task_bind_mode=active_task.bind_mode,
        request_profile=req_profile,
    )
    run_state = AgentRunState(run_id=run_id, goal=effective_goal)
    run_state.transition(
        RunPhase.INIT,
        reason="dispatch_prepared",
        detail={
            "fact_tier": req_profile.tier.value,
            "intent": req_profile.intent.value,
            "transition": turn.transition.value,
            "dispatch": True,
        },
    )

    system = turn.prompt.system if turn.prompt else ""
    logger.info(
        "======== system prompt preview run=%s len=%s transition=%s ========\n%s",
        run_id[:8],
        len(system),
        turn.transition.value,
        system,
    )
    base_messages: list[dict[str, str]] = (
        list(turn.prompt.messages) if turn.prompt else [{"role": "system", "content": system}]
    )

    model = get_chat_model()
    assistant_parts: list[str] = []
    think_parts: list[str] = []
    file_meta: list[dict[str, Any]] = []
    empty_extract_retries = 0
    scratchpad = ReactScratchpad()
    paused_confirm_id: int | None = None
    trajectory_log: list[dict[str, Any]] = []
    blocked_page_streak = 0

    def _emit_traj(step: dict[str, Any]) -> str:
        trajectory_log.append(step)
        return sse("trajectory.step", step)

    yield sse(
        "run.started",
        {
            "run_id": run_id,
            "architecture": "react",
            "dispatch": True,
            "task_id": active_task.task_id,
            "task_bind_mode": active_task.bind_mode,
            "task_transition": turn.transition.value,
            "entity_hits": [h.to_dict() for h in entity_result.hits[:6]],
            "session_summaries": len(summary_views),
            "vector_hits": vector_hit_count,
            "memory_debug": memory_asm.debug,
            "context_soft": bool(turn.context and turn.context.soft_triggered),
            "context_hard": bool(turn.context and turn.context.hard_triggered),
        },
    )
    yield sse("think.open", {"title": "ReAct 推理"})
    async for chunk in _emit_think(
        f"调度层就绪 TaskID={active_task.task_id[:8]}… 模式={active_task.bind_mode}/"
        f"{turn.transition.value} 意图={memory_asm.intent}\n"
    ):
        yield chunk
        think_parts.append(f"task:{active_task.bind_mode}")
        think_parts.append(f"transition:{turn.transition.value}")
        think_parts.append(f"intent:{memory_asm.intent}")
    if entity_result.ok:
        async for chunk in _emit_think(
            "实体匹配命中: "
            + "、".join(entity_result.top_values(limit=3))
            + ("（指代已解析）\n" if entity_result.deictic_resolved else "\n")
        ):
            yield chunk
            think_parts.append("entity_match")
    if memory_asm.ranked:
        async for chunk in _emit_think(
            f"记忆候选 Top{len(memory_asm.ranked)} "
            f"(intent={memory_asm.intent})\n"
        ):
            yield chunk
            think_parts.append("memory_pipeline")

    # 安全硬拦截：违规问题不进工具链
    if is_disallowed_request(user_text) or is_disallowed_request(effective_goal):
        run_state.intercept("safety_block", round_i=0)
        yield _emit_traj(intercept_step("safety_block", round_i=0))
        async for chunk in _emit_think("安全策略：该问题属于禁止回答范围，直接拒答。\n"):
            yield chunk
            think_parts.append("safety_block")
        content = SAFETY_REFUSAL
        run_state.record_finalize(FinalizePath.SAFETY_REFUSAL, content, round_i=0)
        run_state.record_delivered(content)
        run_state.complete()
        yield _emit_traj(finish_step(round_i=0))
        yield sse("react.finish", {"round": 0, "thought": "safety_block", "content": content})
        async for chunk in _emit_answer(content):
            yield chunk
        yield sse("think.close", {})
        _persist_run_state(db, user_id, conversation_id, run_id, run_state, milestone="safety_block")
        db.add(
            Message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="assistant",
                content=content,
                metadata_json=_build_assistant_metadata(
                    run_id=run_id,
                    think_parts=think_parts,
                    scratchpad=scratchpad,
                    trajectory_log=trajectory_log,
                    task_ctx=task_ctx,
                    run_state=run_state,
                    file_meta=file_meta,
                    extra={"safety_block": True},
                ),
            )
        )
        db.commit()
        if task_ctx.task_id:
            update_task_after_turn(
                db,
                task_id=task_ctx.task_id,
                user_id=user_id,
                run_id=run_id,
                answer_preview=content,
            )
        await _compact_session_after_turn(
            db,
            user_id=user_id,
            conversation_id=conversation_id,
            task_id=task_ctx.task_id,
        )
        yield sse(
            "done",
            {
                "run_id": run_id,
                "finalize_path": FinalizePath.SAFETY_REFUSAL.value,
                "task_id": task_ctx.task_id,
            },
        )
        return

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
                "content": build_react_continue_prompt(
                    task_ctx.render(),
                    scratchpad,
                    goal=task_ctx.goal,
                    facts=task_ctx.facts,
                ),
            }
        )

        try:
            raw = await model.chat(messages, temperature=react_params.temperature)
        except (LLMCallError, Exception) as exc:
            logger.warning("react llm failed round=%s: %s", round_i, exc)
            # 模型挂了但还有轮次：自动执行下一步取数，避免空材料编造报告
            more = next_research_tool(
                goal=task_ctx.goal or "",
                facts=task_ctx.facts,
                steps=scratchpad.steps,
                failed_urls=list(task_ctx.urls_to_skip()),
                round_i=round_i,
                max_rounds=agent_max_tool_rounds,
                profile=getattr(task_ctx, "request_profile", None),
            )
            if more and round_i < agent_max_tool_rounds - 1:
                run_state.intercept(
                    "llm_unavailable_auto_tool",
                    round_i=round_i,
                    tool=str(more.get("tool") or ""),
                )
                yield _emit_traj(
                    intercept_step(
                        "llm_unavailable_auto_tool",
                        round_i=round_i,
                        detail=f"{more.get('tool')}: {str(more.get('args') or '')[:100]}",
                    )
                )
                async for chunk in _emit_think(
                    f"模型调用失败，自动继续取数（{more.get('reason')}）…\n"
                ):
                    yield chunk
                    think_parts.append("llm_unavailable_auto_tool")
                parsed = {
                    "action": "tool",
                    "tool": str(more["tool"]),
                    "args": more.get("args") or {},
                    "think": str(more.get("think") or "模型中断后自动取数"),
                }
                think = str(parsed["think"])
                action = "tool"
                raw = ""
            else:
                run_state.intercept("llm_unavailable", round_i=round_i)
                yield _emit_traj(intercept_step("llm_unavailable", round_i=round_i))
                yield sse(
                    "error",
                    {
                        "message": "模型连接暂时中断，正在基于已有结果收束…",
                        "recoverable": True,
                    },
                )
                async for chunk in _emit_think(
                    f"模型调用失败（已重试）：{str(exc)[:120]}。改为基于已有 Observation 收束答案…\n"
                ):
                    yield chunk
                    think_parts.append("llm_unavailable")
                content = await _answer_after_llm_failure(
                    model, task_ctx, round_i=round_i, run_state=run_state
                )
                citations = build_citations(task_ctx.facts)
                if citations:
                    yield sse("citations", {"items": citations})
                yield _emit_traj(finish_step(round_i=round_i))
                scratchpad.add_thought_action("模型不可用，材料收束", "finish", content, round_i)
                run_state.record_delivered(content)
                yield sse(
                    "react.finish",
                    {"round": round_i, "thought": "llm_unavailable", "content": content[:500]},
                )
                async for chunk in _emit_answer(content):
                    yield chunk
                assistant_parts = [content]
                break
        else:
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
                    preferred_tool=required_file_write_tool(task_ctx.goal or ""),
                )
                if recovered:
                    run_state.intercept("file_claim_recover", round_i=round_i)
                    yield _emit_traj(intercept_step("file_claim_recover", round_i=round_i))
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
                # 过早 finish：按 A/B/C 档位路由（C 不强制检索；A 强制检索）
                tier = getattr(
                    getattr(task_ctx, "request_profile", None), "tier", FactTier.B
                )
                if (
                    not task_ctx.facts
                    and round_i < agent_max_tool_rounds - 1
                    and tier != FactTier.C
                    and not _skip_premature_auto_search(task_ctx.goal or "")
                    and (
                        tier == FactTier.A
                        or not re.match(r"^\s*(什么是|什么叫|何为|谁是)", task_ctx.goal or "")
                    )
                ):
                    run_state.intercept("premature_finish_auto_search", round_i=round_i)
                    yield _emit_traj(
                        intercept_step(
                            "premature_finish_auto_search",
                            round_i=round_i,
                            detail=(
                                "A 类高事实清单，先检索再答"
                                if tier == FactTier.A
                                else "尚未拿到有效材料，先搜索"
                            ),
                        )
                    )
                    async for chunk in _emit_think(
                        (
                            "A 类请求：强制先检索再 finish…\n"
                            if tier == FactTier.A
                            else "尚未拿到有效 Observation，先 web_search 再决策…\n"
                        )
                    ):
                        yield chunk
                    q = task_ctx.goal
                    prof = getattr(task_ctx, "request_profile", None)
                    if prof and getattr(prof, "search_queries", None):
                        q = prof.search_queries[0]
                    parsed = {
                        "action": "tool",
                        "tool": "web_search",
                        "args": {"query": q},
                        "think": "自动补搜索",
                    }
                    action = "tool"
                else:
                    if not content:
                        content = ""
                    # 空壳 finish：若 thought/搜索事实已能补全则直接交付；
                    # 深度任务 / 材料不足：强制继续搜索或抓正文
                    enriched_preview = enrich_finish_answer(
                        content,
                        thought=think,
                        facts=task_ctx.facts,
                        goal=task_ctx.goal or "",
                    )
                    more = next_research_tool(
                        goal=task_ctx.goal or "",
                        facts=task_ctx.facts,
                        steps=scratchpad.steps,
                        failed_urls=list(task_ctx.urls_to_skip()),
                        round_i=round_i,
                        max_rounds=agent_max_tool_rounds,
                        profile=getattr(task_ctx, "request_profile", None),
                    )
                    # 硬门控：有 hits 无 body / 深度材料不足 → 禁止 finish
                    if not more:
                        ok_finish, block_reason = can_finish_research(
                            goal=task_ctx.goal or "",
                            facts=task_ctx.facts,
                            steps=scratchpad.steps,
                            failed_urls=list(task_ctx.urls_to_skip()),
                        )
                        if not ok_finish and round_i < agent_max_tool_rounds - 1:
                            more = next_research_tool(
                                goal=task_ctx.goal or "",
                                facts=task_ctx.facts,
                                steps=scratchpad.steps,
                                failed_urls=list(task_ctx.urls_to_skip()),
                                round_i=round_i,
                                max_rounds=agent_max_tool_rounds,
                            )
                            if not more and block_reason == "search_hits_no_body":
                                next_url = pick_fetch_url(task_ctx.facts, skip=task_ctx.urls_to_skip(), goal=task_ctx.goal or "")
                                if next_url:
                                    more = {
                                        "tool": "web_fetch",
                                        "args": {"url": next_url},
                                        "think": "有搜索结果但无正文，禁止直接 finish",
                                        "reason": "search_hits_no_body",
                                    }
                    # 兼容：仅有搜索标题时也要抓
                    if not more:
                        fetched_already = any(
                            s.action
                            in {"web_fetch", "http_request", "browser_extract", "browser_navigate"}
                            for s in scratchpad.steps
                        )
                        next_url = pick_fetch_url(task_ctx.facts, skip=task_ctx.urls_to_skip(), goal=task_ctx.goal or "")
                        if (
                            next_url
                            and not fetched_already
                            and round_i < agent_max_tool_rounds - 1
                            and (
                                search_only_needs_fetch(
                                    task_ctx.facts, fetched_already=fetched_already
                                )
                                or (
                                    is_hollow_answer(content)
                                    and is_hollow_answer(enriched_preview)
                                )
                            )
                        ):
                            more = {
                                "tool": "web_fetch",
                                "args": {"url": next_url},
                                "think": "搜索后自动抓取内容页",
                                "reason": "auto_web_fetch",
                            }
                    # 计数清单：条数不足 → A 类荐书优先 Open Library，否则补搜
                    if (
                        not more
                        and is_count_list_goal(task_ctx.goal or "")
                        and is_count_shortfall(
                            enriched_preview or content, task_ctx.goal or ""
                        )
                        and round_i < agent_max_tool_rounds - 1
                    ):
                        from agent.research_policy import (
                            openlibrary_args_fingerprint,
                            openlibrary_discover_args,
                            prefers_openlibrary_catalog,
                            prior_openlibrary_fingerprints,
                        )

                        prof = getattr(task_ctx, "request_profile", None)
                        tier = getattr(prof, "tier", None)
                        ol_on = False
                        try:
                            from config import config as cfg

                            ol_on = bool(getattr(cfg, "openlibrary_enabled", False))
                        except Exception:
                            ol_on = False
                        if (
                            ol_on
                            and tier == FactTier.A
                            and prefers_openlibrary_catalog(task_ctx.goal or "")
                        ):
                            ol_args = openlibrary_discover_args(task_ctx.goal or "")
                            fp = openlibrary_args_fingerprint(ol_args)
                            if fp not in prior_openlibrary_fingerprints(scratchpad.steps):
                                more = {
                                    "tool": "openlibrary_lookup",
                                    "args": ol_args,
                                    "think": "A 类清单条数不足，用书目库发现补齐",
                                    "reason": "count_shortfall",
                                }
                        if not more:
                            alts = alt_search_queries(
                                task_ctx.goal or "",
                                prior_search_queries(scratchpad.steps),
                            )
                            if alts:
                                more = {
                                    "tool": "web_search",
                                    "args": {"query": alts[0]},
                                    "think": "清单条数不足目标，继续检索具体条目",
                                    "reason": "count_shortfall",
                                }
                            else:
                                next_url = pick_fetch_url(
                                    task_ctx.facts,
                                    skip=task_ctx.urls_to_skip(),
                                    goal=task_ctx.goal or "",
                                )
                                if next_url:
                                    more = {
                                        "tool": "web_fetch",
                                        "args": {"url": next_url},
                                        "think": "清单条数不足，再抓一页提炼条目",
                                        "reason": "count_shortfall",
                                    }
                    if more:
                        tool_n = str(more["tool"])
                        args_n = more.get("args") or {}
                        reason = str(more.get("reason") or "need_more_research")
                        # 保留已写出的实质 finish，避免后续空壳/来源清单覆盖
                        if content and is_substantive_draft(
                            content, task_ctx.goal or "", facts=task_ctx.facts
                        ):
                            prev = getattr(run_state, "react_finish_draft", "") or ""
                            if answer_depth_score(content) >= answer_depth_score(prev):
                                run_state.react_finish_draft = content
                        run_state.intercept(reason, round_i=round_i, tool=tool_n)
                        yield _emit_traj(
                            intercept_step(
                                reason,
                                round_i=round_i,
                                detail=f"{tool_n}: {str(args_n)[:100]}",
                            )
                        )
                        async for chunk in _emit_think(
                            f"材料不足，自动继续取数（{reason}）: {tool_n} {str(args_n)[:100]}\n"
                        ):
                            yield chunk
                        parsed = {
                            "action": "tool",
                            "tool": tool_n,
                            "args": args_n,
                            "think": str(more.get("think") or "继续调研"),
                        }
                        action = "tool"
                    else:
                        # 材料已尽：若约束要求文档且尚未落盘，先写文件再交付
                        req_write = required_file_write_tool(task_ctx.goal or "")
                        if (
                            req_write
                            and not task_ctx.artifacts
                            and round_i < agent_max_tool_rounds - 1
                        ):
                            recovered = _recover_file_tool(
                                raw,
                                think,
                                content,
                                tools,
                                goal=task_ctx.goal,
                                facts=task_ctx.facts,
                                preferred_tool=req_write,
                            ) or _force_file_write_action(
                                tool=req_write,
                                goal=task_ctx.goal or "",
                                think=think,
                                content=content,
                                facts=task_ctx.facts,
                            )
                            run_state.intercept(
                                "missing_file_write",
                                round_i=round_i,
                                tool=str(recovered.get("tool") or req_write),
                            )
                            yield _emit_traj(
                                intercept_step(
                                    "missing_file_write",
                                    round_i=round_i,
                                    detail=str(recovered.get("tool") or req_write),
                                )
                            )
                            async for chunk in _emit_think(
                                f"约束要求输出文档，自动调用 {recovered.get('tool')}…\n"
                            ):
                                yield chunk
                            if content and is_substantive_draft(
                                content, task_ctx.goal or "", facts=task_ctx.facts
                            ):
                                run_state.react_finish_draft = content
                            parsed = recovered
                            action = "tool"
                        else:
                            ok_f, br = can_finish_research(
                                goal=task_ctx.goal or "",
                                facts=task_ctx.facts,
                                steps=scratchpad.steps,
                                failed_urls=list(task_ctx.urls_to_skip()),
                            )
                            if br == "weak_materials":
                                run_state.intercept("weak_materials", round_i=round_i)
                                yield _emit_traj(
                                    intercept_step("weak_materials", round_i=round_i)
                                )
                                async for chunk in _emit_think(
                                    "材料偏弱且无更多可抓来源，强制充实成稿后再交付…\n"
                                ):
                                    yield chunk
                            run_state.react_finish_draft = content
                            run_state.snapshot_answer(
                                "react_finish",
                                content,
                                round_i=round_i,
                                fact_count=len(task_ctx.facts),
                                path=br or "",
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
                            citations = build_citations(task_ctx.facts)
                            if citations:
                                yield sse("citations", {"items": citations})
                            yield _emit_traj(finish_step(round_i=round_i, detail="已交付"))
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

            # 仅拦截：用户目标违规，或搜索类 query 本身违规（勿扫 file_write/长正文）
            if is_disallowed_request(task_ctx.goal or ""):
                run_state.intercept("safety_block", round_i=round_i)
                yield _emit_traj(intercept_step("safety_block", round_i=round_i))
                content = SAFETY_REFUSAL
                run_state.record_finalize(FinalizePath.SAFETY_REFUSAL, content, round_i=round_i)
                run_state.record_delivered(content)
                yield _emit_traj(finish_step(round_i=round_i))
                yield sse(
                    "react.finish",
                    {"round": round_i, "thought": "safety_block", "content": content},
                )
                async for chunk in _emit_answer(content):
                    yield chunk
                assistant_parts = [content]
                break
            if tool in {"web_search", "kb_search", "web_fetch", "browser_navigate"}:
                q_check = ""
                if isinstance(args, dict):
                    q_check = str(args.get("query") or args.get("url") or "")
                elif isinstance(args, str):
                    q_check = args
                if q_check and is_disallowed_request(q_check):
                    run_state.intercept("safety_block", round_i=round_i)
                    yield _emit_traj(intercept_step("safety_block", round_i=round_i))
                    content = SAFETY_REFUSAL
                    run_state.record_finalize(FinalizePath.SAFETY_REFUSAL, content, round_i=round_i)
                    run_state.record_delivered(content)
                    yield _emit_traj(finish_step(round_i=round_i))
                    yield sse(
                        "react.finish",
                        {"round": round_i, "thought": "safety_block", "content": content},
                    )
                    async for chunk in _emit_answer(content):
                        yield chunk
                    assistant_parts = [content]
                    break

            # 写文件：先补全正文，避免生成空文件
            if tool.startswith("file_write_"):
                args = await _ensure_file_write_content(
                    model,
                    tool,
                    args if isinstance(args, dict) else {},
                    goal=task_ctx.goal or "",
                    think=think,
                    facts=task_ctx.facts,
                )

            # 入参校验/归一化（通用契约，不做业务强制改写）
            norm, verr = validate_and_normalize_args(tool, args)
            if verr and tool.startswith("file_write_"):
                # 再尝试用合成器硬补一次
                args = await _ensure_file_write_content(
                    model,
                    tool,
                    {
                        **(args if isinstance(args, dict) else {}),
                        "content": str((args or {}).get("content") or think or ""),
                    },
                    goal=task_ctx.goal or "",
                    think=think,
                    facts=task_ctx.facts,
                )
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

            # 相同/近义 web_search 须在记入 scratchpad 之前判断，否则会把自己算成「已搜过」而永远不执行
            if tool == "web_search":
                q = str((args or {}).get("query") or "").strip()
                prior_q = [
                    str((s.action_input or {}).get("query") or "").strip()
                    if isinstance(s.action_input, dict)
                    else ""
                    for s in scratchpad.steps
                    if s.action == "web_search"
                ]
                searches_done = count_search_steps(scratchpad.steps)
                near_dup = bool(q and is_near_duplicate_search_query(q, prior_q))
                next_u = pick_fetch_url(task_ctx.facts, skip=task_ctx.urls_to_skip(), goal=task_ctx.goal or "")
                # 已有搜索命中却仍反复搜 → 优先去抓正文，避免近义 query 空转
                prefer_fetch = bool(
                    next_u
                    and (
                        near_dup
                        or (
                            searches_done >= 2
                            and has_search_hit_facts(task_ctx.facts)
                        )
                    )
                )
                if near_dup or prefer_fetch:
                    reason_key = "duplicate_web_search" if near_dup else "search_hits_prefer_fetch"
                    run_state.intercept(reason_key, round_i=round_i, query=q[:80])
                    yield _emit_traj(
                        intercept_step(
                            reason_key,
                            round_i=round_i,
                            detail=(
                                f"已搜过近义「{q[:40]}」"
                                if near_dup
                                else f"已搜索 {searches_done} 次，改为抓取正文"
                            ),
                        )
                    )
                    if prefer_fetch and next_u:
                        tip_msg = (
                            f"近义搜索已执行过「{q[:40]}」，改为 web_fetch: {next_u[:100]}\n"
                            if near_dup
                            else f"已有搜索结果，停止重复搜索，改为 web_fetch: {next_u[:100]}\n"
                        )
                        async for chunk in _emit_think(tip_msg):
                            yield chunk
                        tool = "web_fetch"
                        args = {"url": next_u}
                    elif task_ctx.facts and near_dup:
                        tip = "相同/近义搜索词已执行过，请基于已有 Observation finish，勿重复搜索。"
                        scratchpad.add_thought_action(think, tool, args, round_i)
                        scratchpad.set_observation(tip)
                        yield sse("react.observation", {"round": round_i, "observation": tip, "tool": tool})
                        async for chunk in _emit_think(f"Observation: {tip}\n"):
                            yield chunk
                        continue
                    # 无 facts 却重复搜：换 query 再试一次，不要空转
                    elif near_dup and round_i < agent_max_tool_rounds - 1:
                        alt_q = task_ctx.goal or q
                        if alt_q != q and not is_near_duplicate_search_query(alt_q, prior_q + [q]):
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

            # 禁止对已失败 / 已成功抓取的 URL 死循环重试
            from agent.context import normalize_url

            nav_url = normalize_url(str(args.get("url") or ""))
            if tool in {"web_fetch", "browser_navigate", "http_request"} and nav_url:
                if task_ctx.url_already_seen(nav_url):
                    tip = f"URL 本轮已抓取/失败过，跳过重复打开: {nav_url[:120]}"
                    scratchpad.add_thought_action(think, tool, args, round_i)
                    scratchpad.set_observation(tip)
                    yield sse(
                        "react.observation",
                        {"round": round_i, "observation": tip, "tool": tool},
                    )
                    async for chunk in _emit_think(f"Observation: {tip}\n"):
                        yield chunk
                    task_ctx.add_step(tip)
                    next_u = pick_fetch_url(
                        task_ctx.facts,
                        skip=task_ctx.urls_to_skip(),
                        goal=task_ctx.goal or "",
                    )
                    if next_u and normalize_url(next_u) != nav_url and round_i < agent_max_tool_rounds - 1:
                        async for chunk in _emit_think(f"改抓下一来源: {next_u[:80]}\n"):
                            yield chunk
                        tool = "web_fetch"
                        args = {"url": next_u}
                        nav_url = normalize_url(next_u)
                    else:
                        alts = alt_search_queries(
                            task_ctx.goal or "",
                            prior_search_queries(scratchpad.steps),
                        )
                        if alts and round_i < agent_max_tool_rounds - 1:
                            async for chunk in _emit_think(
                                f"无更多可抓链接，换关键词搜索: {alts[0][:60]}\n"
                            ):
                                yield chunk
                            tool = "web_search"
                            args = {"query": alts[0]}
                            nav_url = ""
                        else:
                            continue
                elif task_ctx.already_failed(tool, args, limit=1):
                    tip = f"检测到重复失败调用 {tool}，已拦截。请换策略或直接总结已有信息。"
                    scratchpad.set_observation(tip)
                    yield sse(
                        "react.observation",
                        {"round": round_i, "observation": tip, "tool": tool},
                    )
                    async for chunk in _emit_think(f"Observation: {tip}\n"):
                        yield chunk
                    task_ctx.add_step(f"拦截重复失败: {tool} {nav_url}")
                    continue
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
            yield _emit_traj(action_step(tool, args, round_i=round_i, status="running"))

            if tool in CONFIRM_TOOLS:
                ckpt = build_confirm_checkpoint(
                    tool=tool,
                    args=args if isinstance(args, dict) else {"_raw": args},
                    task_ctx=task_ctx,
                    scratchpad=scratchpad,
                    round_i=round_i,
                    run_id=run_id,
                    tools=tools,
                    effective_goal=effective_goal,
                )
                conf = Confirmation(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    run_id=run_id,
                    action_type=tool,
                    payload_json=json.dumps(ckpt, ensure_ascii=False),
                    status="pending",
                )
                db.add(conf)
                db.commit()
                db.refresh(conf)
                yield _emit_traj(
                    action_step(tool, args, round_i=round_i, status="pending", reason="awaiting_confirm")
                )
                yield sse(
                    "confirmation.required",
                    {
                        "id": conf.id,
                        "action_type": tool,
                        "action_label": confirm_tool_label(tool),
                        "args": args,
                        "expires_in": confirmation_ttl_sec,
                    },
                )
                notice = (
                    f"需要你确认：{confirm_tool_label(tool)}。"
                    "请在确认条中同意或拒绝；同意后将继续执行并完成任务。"
                )
                async for chunk in _emit_answer(notice):
                    yield chunk
                assistant_parts = [notice]
                paused_confirm_id = conf.id
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
            if isinstance(result, dict):
                await _maybe_index_tool_observation(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    task_id=task_ctx.task_id,
                    tool=tool,
                    result=result,
                    run_id=run_id,
                )

            # 验证码/风控：立刻换下一条内容链接 web_fetch（不问用户选编号）
            cur_url = str((args or {}).get("url") or (result.get("url") if isinstance(result, dict) else "") or "")
            if (
                tool in {"web_fetch", "browser_navigate", "http_request", "browser_extract"}
                and isinstance(result, dict)
                and _is_blocked_page(result, cur_url)
                and round_i < agent_max_tool_rounds - 1
            ):
                blocked_page_streak += 1
                if cur_url:
                    task_ctx.mark_failed_url(cur_url)
                next_u = pick_fetch_url(task_ctx.facts, skip=task_ctx.urls_to_skip(), goal=task_ctx.goal or "")
                tip_block = f"命中验证码/风控页，跳过: {cur_url[:100]}"
                async for chunk in _emit_think(tip_block + "\n"):
                    yield chunk
                scratchpad.set_observation(tip_block)
                if blocked_page_streak >= 2 and not next_u:
                    async for chunk in _emit_think(
                        "连续多次页面被拦截且无更多来源，改为基于已有材料或常识总结…\n"
                    ):
                        yield chunk
                    content = await _finalize_user_answer(
                        model, task_ctx, "", round_i=round_i + 1, thought=think, run_state=run_state
                    )
                    scratchpad.add_thought_action("连续拦截后兜底", "finish", content, round_i)
                    scratchpad.set_observation("（连续验证码/风控，已兜底）")
                    run_state.record_delivered(content)
                    yield sse("react.finish", {"round": round_i, "thought": "blocked_fallback", "content": content[:500]})
                    async for chunk in _emit_answer(content):
                        yield chunk
                    assistant_parts = [content]
                    break
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
                        blocked_page_streak += 1
                    else:
                        blocked_page_streak = 0
            elif tool in {"web_fetch", "browser_navigate", "http_request"} and isinstance(result, dict):
                if not _is_blocked_page(result, cur_url) and task_ctx.last_ok:
                    blocked_page_streak = 0

            if isinstance(result, dict) and result.get("frame"):
                yield sse("browser.frame", {"url": result.get("url"), "frame": result["frame"]})
            if isinstance(result, dict) and result.get("file_id"):
                item = {"file_id": result["file_id"], "name": result.get("name")}
                file_meta.append(item)
                yield sse("file.ready", item)
            elif (
                isinstance(result, dict)
                and tool.startswith("file_write_")
                and (result.get("ok") is False or result.get("error"))
            ):
                # 写文件失败：明确 Observation，禁止后续空喊「已生成」
                fail_msg = str(result.get("error") or "写文件失败，未落盘")
                async for chunk in _emit_think(f"写文件未成功：{fail_msg}\n"):
                    yield chunk
                task_ctx.add_step(f"{tool} 失败: {fail_msg}")

            obs = format_observation(tool, result)
            scratchpad.set_observation(obs)
            run_state.record_tool_done(
                tool,
                bool(task_ctx.last_ok),
                summary=obs[:400],
            )
            fail_reason = ""
            if not task_ctx.last_ok:
                fail_reason = (task_ctx.last_error or obs or "执行失败")[:160]
            elif isinstance(result, dict) and _is_blocked_page(result, cur_url):
                fail_reason = "页面被验证码或风控拦截"
            yield _emit_traj(
                observation_step(
                    tool,
                    round_i=round_i,
                    ok=bool(task_ctx.last_ok) and not fail_reason,
                    summary=obs,
                    reason=fail_reason,
                )
            )
            if tool == "web_search" and task_ctx.last_ok:
                n_hits = len(extract_search_hit_cards(task_ctx.facts))
                if n_hits:
                    yield _emit_traj(
                        {
                            "round": round_i,
                            "kind": "search",
                            "title": "搜索完成",
                            "detail": f"已找到 {n_hits} 条结果，准备打开正文",
                            "status": "ok",
                            "reason": "",
                            "tool": "web_search",
                        }
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

            # 多轮仍无与目标相关实质事实：先尝试继续取数，再知识兜底
            if needs_knowledge_fallback(task_ctx.goal, task_ctx.facts, round_i + 1):
                more_fb = next_research_tool(
                    goal=task_ctx.goal or "",
                    facts=task_ctx.facts,
                    steps=scratchpad.steps,
                    failed_urls=list(task_ctx.urls_to_skip()),
                    round_i=round_i,
                    max_rounds=agent_max_tool_rounds,
                )
                if more_fb and round_i < agent_max_tool_rounds - 1:
                    tool_n = str(more_fb["tool"])
                    args_n = more_fb.get("args") or {}
                    reason = str(more_fb.get("reason") or "need_more_research")
                    run_state.intercept(reason, round_i=round_i, tool=tool_n)
                    yield _emit_traj(
                        intercept_step(reason, round_i=round_i, detail=f"{tool_n}")
                    )
                    async for chunk in _emit_think(
                        f"材料仍不足，继续取数后再答（{reason}）…\n"
                    ):
                        yield chunk
                    # 直接执行下一步工具，避免空兜底
                    parsed = {
                        "action": "tool",
                        "tool": tool_n,
                        "args": args_n,
                        "think": str(more_fb.get("think") or "继续调研"),
                    }
                    # 落入下方 tool 分支需 continue 到下一轮让模型走；此处手动跑一轮取数
                    tip = f"Action: {tool_n} {json.dumps(args_n, ensure_ascii=False)}"
                    async for chunk in _emit_think(tip + "\n"):
                        yield chunk
                    yield sse("tool.started", {"tool": tool_n, "args": args_n, "round": round_i})
                    try:
                        result_fb = await execute_tool(
                            tool_n,
                            args_n if isinstance(args_n, dict) else {},
                            db=db,
                            user_id=user_id,
                            conversation_id=conversation_id,
                        )
                    except Exception as exc:
                        result_fb = {"error": str(exc)}
                    if not isinstance(result_fb, dict):
                        result_fb = {"error": "bad result"}
                    apply_result_to_context(task_ctx, tool_n, result_fb, args=args_n if isinstance(args_n, dict) else {})
                    obs_fb = format_observation(tool_n, result_fb)
                    scratchpad.add_thought_action(
                        str(more_fb.get("think") or "继续调研"), tool_n, args_n, round_i
                    )
                    scratchpad.set_observation(obs_fb)
                    yield sse("react.observation", {"round": round_i, "observation": obs_fb, "tool": tool_n})
                    yield sse("tool.finished", {"tool": tool_n, "result": _shrink(result_fb)})
                    continue
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

    # 优雅暂停：等待用户确认，不走终稿兜底覆盖
    if paused_confirm_id is not None:
        yield sse("think.close", {})
        notice = _user_facing_text("".join(assistant_parts).strip()) or (
            "需要你确认操作后继续。"
        )
        db.add(
            Message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="assistant",
                content=notice,
                metadata_json=_build_assistant_metadata(
                    run_id=run_id,
                    think_parts=think_parts,
                    scratchpad=scratchpad,
                    trajectory_log=trajectory_log,
                    task_ctx=task_ctx,
                    run_state=run_state,
                    file_meta=file_meta,
                    extra={"paused": True, "confirmation_id": paused_confirm_id},
                ),
            )
        )
        db.commit()
        yield sse(
            "done",
            {
                "run_id": run_id,
                "paused": True,
                "confirmation_id": paused_confirm_id,
            },
        )
        return

    yield sse("think.close", {})
    final_text = _user_facing_text("".join(assistant_parts).strip()) or ""
    if not final_text or looks_like_internal(final_text) or not answer_relevant_to_goal(
        final_text, task_ctx.goal or ""
    ):
        final_text = await _finalize_user_answer(
            model, task_ctx, final_text, round_i=agent_max_tool_rounds, run_state=run_state
        )
    final_text = strip_pick_number_prompts(final_text)
    final_text = enforce_safety_answer(goal=task_ctx.goal or "", answer=final_text)
    # 禁止空喊「已生成文件」：无产物则改口，有产物则附下载提示
    if not is_safety_refusal(final_text) and _claims_file_without_artifact(final_text) and not task_ctx.artifacts:
        final_text = strip_pick_number_prompts(
            re.sub(
                r"(已生成|生成了|写好了|文档已|文件已).{0,40}(文档|文件|docx|xlsx|pdf|pptx)[^\n]*",
                "",
                final_text,
                flags=re.I,
            ).strip()
        )
        if not final_text or is_hollow_answer(final_text):
            final_text = (
                "这一轮没能成功生成可下载文件（正文可能为空或写文件失败）。"
                "请再说一次要生成的内容和格式，我会重新写入工作区。"
            )
        else:
            final_text = (
                final_text.rstrip()
                + "\n\n（说明：本轮未能落盘生成文件，如需文档请明确格式后重试。）"
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
    citations = build_citations(task_ctx.facts)
    if citations:
        yield sse("citations", {"items": citations})
    db.add(
        Message(
            conversation_id=conversation_id,
            user_id=user_id,
            role="assistant",
            content=final_text,
            metadata_json=_build_assistant_metadata(
                run_id=run_id,
                think_parts=think_parts,
                scratchpad=scratchpad,
                trajectory_log=trajectory_log,
                task_ctx=task_ctx,
                run_state=run_state,
                file_meta=file_meta,
                citations=citations,
                extra={"entity_hits": [h.to_dict() for h in entity_result.hits[:6]]},
            ),
        )
    )
    db.commit()
    if task_ctx.task_id:
        await dispatch.archiver.archive_turn_await(
            db,
            user_id=user_id,
            session_id=conversation_id,
            task_id=task_ctx.task_id,
            run_id=run_id,
            user_text=user_text,
            answer_preview=final_text[:500],
            artifacts=list(task_ctx.artifacts),
        )
    else:
        await _compact_session_after_turn(
            db,
            user_id=user_id,
            conversation_id=conversation_id,
            task_id=task_ctx.task_id,
        )
    yield sse(
        "done",
        {
            "run_id": run_id,
            "finalize_path": run_state.finalize_path,
            "task_id": task_ctx.task_id,
            "task_bind_mode": task_ctx.task_bind_mode,
            "entity_hits": [h.to_dict() for h in entity_result.hits[:6]],
        },
    )


async def resume_after_confirmation(
    db: Session,
    *,
    user_id: int,
    confirmation_id: int,
    approved: bool,
) -> dict:
    """兼容旧 JSON 接口：拒绝直接处理；同意提示走 SSE resume。"""
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

    if not approved:
        conf.status = "rejected"
        conf.resolved_at = datetime.utcnow()
        db.commit()
        db.add(
            Message(
                conversation_id=conf.conversation_id,
                user_id=user_id,
                role="assistant",
                content="已拒绝该操作，任务中止。如需继续请换一种说法再试。",
                metadata_json=json.dumps(
                    {"confirmation_id": confirmation_id, "status": "rejected"},
                    ensure_ascii=False,
                ),
            )
        )
        db.commit()
        return {"ok": True, "status": "rejected"}

    return {
        "ok": True,
        "status": "pending_resume",
        "need_resume_stream": True,
        "confirmation_id": confirmation_id,
    }


async def resume_chat_after_confirmation(
    db: Session,
    *,
    user_id: int,
    confirmation_id: int,
    approved: bool,
) -> AsyncIterator[str]:
    """SSE 续跑：同意则恢复检查点、执行工具并继续 ReAct；拒绝则短答复结束。"""
    conf = db.get(Confirmation, confirmation_id)
    if not conf or conf.user_id != user_id:
        yield sse("error", {"message": "确认单不存在"})
        yield sse("done", {"ok": False})
        return
    if conf.status != "pending":
        yield sse("error", {"message": "确认单已处理"})
        yield sse("done", {"ok": False})
        return
    if conf.created_at and datetime.utcnow() - conf.created_at > timedelta(seconds=confirmation_ttl_sec):
        conf.status = "expired"
        conf.resolved_at = datetime.utcnow()
        db.commit()
        yield sse("error", {"message": "确认已过期"})
        yield sse("done", {"ok": False})
        return

    conversation_id = conf.conversation_id
    ckpt = parse_checkpoint(conf.payload_json)
    run_id = str(ckpt.get("run_id") or conf.run_id or uuid.uuid4().hex)
    tool = str(ckpt.get("tool") or conf.action_type or "")
    args = ckpt.get("args") if isinstance(ckpt.get("args"), dict) else {}
    start_round = int(ckpt.get("round_i") or 0) + 1
    effective_goal = str(ckpt.get("effective_goal") or "")
    tools_ckpt = list(ckpt.get("tools") or [])

    if not approved:
        conf.status = "rejected"
        conf.resolved_at = datetime.utcnow()
        db.commit()
        notice = "已拒绝该操作，任务中止。如需继续请换一种说法再试。"
        yield sse("think.open", {"title": "确认结果"})
        async for chunk in _emit_answer(notice):
            yield chunk
        yield sse("think.close", {})
        db.add(
            Message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="assistant",
                content=notice,
                metadata_json=json.dumps(
                    {"confirmation_id": confirmation_id, "status": "rejected", "run_id": run_id},
                    ensure_ascii=False,
                ),
            )
        )
        db.commit()
        yield sse("done", {"ok": True, "status": "rejected", "run_id": run_id})
        return

    conf.status = "approved"
    conf.resolved_at = datetime.utcnow()
    db.commit()

    task_ctx = restore_task_context(ckpt.get("task_context") if isinstance(ckpt.get("task_context"), dict) else {})
    if effective_goal and not task_ctx.goal:
        task_ctx.goal = effective_goal
    scratchpad = restore_scratchpad(ckpt.get("react_steps") if isinstance(ckpt.get("react_steps"), list) else [])
    run_state = AgentRunState(run_id=run_id, goal=task_ctx.goal or effective_goal)
    run_state.transition(RunPhase.EXECUTING, round_i=start_round - 1, reason="resume_after_confirm")
    trajectory_log: list[dict[str, Any]] = []

    def _emit_traj(step: dict[str, Any]) -> str:
        trajectory_log.append(step)
        return sse("trajectory.step", step)

    skills = _active_skills(db, user_id)
    tools, skill_body = _merge_tools(skills)
    if tools_ckpt:
        # 合并检查点工具与当前可用工具
        for t in tools_ckpt:
            if t not in tools:
                tools.append(t)
    memory_raw = build_memory_context(db, user_id)
    memory_ctx = filter_long_term_memory_lines(memory_raw, task_ctx.goal)

    system = SYSTEM_PROMPT + f"\n\n可用工具: {json.dumps(tools, ensure_ascii=False)}\n\n"
    system += render_tool_contracts(tools) + "\n\n" + skill_body
    if memory_ctx:
        system += f"\n\n# 长期用户记忆（已按当前目标过滤）\n{memory_ctx}"
    system += (
        "\n\n# 记忆纪律\n"
        "1. 独立新问题与上一轮硬隔离：禁止联想/提及上一轮书名、新闻或结论。\n"
        "2. 仅当用户明确追问/续作才使用最近同题上下文。\n"
        "3. finish 必须是用户可读终稿。\n"
        "4. 只读搜索/抓取无需用户确认；自行 web_fetch 后总结交付。\n"
        f"\n\n{SAFETY_POLICY_PROMPT}\n"
    )

    history = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.id.asc())
        .limit(40)
        .all()
    )
    base_messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    base_messages.extend(
        build_dialog_messages(
            history,
            current_goal=task_ctx.goal,
            sanitize_fn=sanitize_public_answer,
            looks_internal_fn=looks_like_internal,
        )
    )

    model = get_chat_model()
    assistant_parts: list[str] = []
    think_parts: list[str] = ["确认后续跑"]
    file_meta: list[dict[str, Any]] = []
    empty_extract_retries = 0

    yield sse("run.started", {"run_id": run_id, "architecture": "react", "resumed": True})
    yield sse("think.open", {"title": "确认后续跑"})
    async for chunk in _emit_think(f"用户已同意：{confirm_tool_label(tool)}，继续执行…\n"):
        yield chunk

    # 执行已批准工具
    yield sse("tool.started", {"tool": tool, "args": args, "round": max(0, start_round - 1)})
    yield _emit_traj(action_step(tool, args, round_i=max(0, start_round - 1), status="running"))
    run_state.record_tool_start(tool, args)
    try:
        result = await execute_tool(
            tool,
            args,
            db=db,
            user_id=user_id,
            conversation_id=conversation_id,
        )
    except Exception as exc:
        logger.warning("resume tool failed: %s %s", tool, exc)
        result = {"error": str(exc)}
    if not isinstance(result, dict):
        result = {"error": "bad result"}

    apply_result_to_context(task_ctx, tool, result, args=args)
    if isinstance(result, dict) and result.get("frame"):
        yield sse("browser.frame", {"url": result.get("url"), "frame": result["frame"]})
    if isinstance(result, dict) and result.get("file_id"):
        item = {"file_id": result["file_id"], "name": result.get("name")}
        file_meta.append(item)
        yield sse("file.ready", item)

    obs = format_observation(tool, result)
    scratchpad.add_thought_action("用户已确认，执行操作", tool, args, max(0, start_round - 1))
    scratchpad.set_observation(obs)
    run_state.record_tool_done(tool, bool(task_ctx.last_ok), summary=obs[:400])
    yield _emit_traj(
        observation_step(tool, round_i=max(0, start_round - 1), ok=bool(task_ctx.last_ok), summary=obs)
    )
    yield sse("react.observation", {"round": max(0, start_round - 1), "observation": obs, "tool": tool})
    yield sse("tool.finished", {"tool": tool, "result": _shrink(result)})
    async for chunk in _emit_think(f"Observation: {obs}\n"):
        yield chunk

    # 继续 ReAct 剩余轮次
    for round_i in range(start_round, agent_max_tool_rounds):
        run_state.begin_round(round_i)
        messages = compact_history(base_messages, limit_pairs=4)
        messages.append(
            {
                "role": "user",
                "content": build_react_continue_prompt(
                    task_ctx.render(),
                    scratchpad,
                    goal=task_ctx.goal,
                    facts=task_ctx.facts,
                ),
            }
        )
        try:
            raw = await model.chat(messages, temperature=0.2)
        except (LLMCallError, Exception) as exc:
            logger.warning("resume react llm failed round=%s: %s", round_i, exc)
            more = next_research_tool(
                goal=task_ctx.goal or "",
                facts=task_ctx.facts,
                steps=scratchpad.steps,
                failed_urls=list(task_ctx.urls_to_skip()),
                round_i=round_i,
                max_rounds=agent_max_tool_rounds,
                profile=getattr(task_ctx, "request_profile", None),
            )
            if more and round_i < agent_max_tool_rounds - 1:
                run_state.intercept(
                    "llm_unavailable_auto_tool",
                    round_i=round_i,
                    tool=str(more.get("tool") or ""),
                )
                yield _emit_traj(
                    intercept_step(
                        "llm_unavailable_auto_tool",
                        round_i=round_i,
                        detail=f"{more.get('tool')}: {str(more.get('args') or '')[:100]}",
                    )
                )
                async for chunk in _emit_think(
                    f"模型调用失败，自动继续取数（{more.get('reason')}）…\n"
                ):
                    yield chunk
                    think_parts.append("llm_unavailable_auto_tool")
                parsed = {
                    "action": "tool",
                    "tool": str(more["tool"]),
                    "args": more.get("args") or {},
                    "think": str(more.get("think") or "模型中断后自动取数"),
                }
                think = str(parsed["think"])
                action = "tool"
                raw = ""
            else:
                run_state.intercept("llm_unavailable", round_i=round_i)
                yield _emit_traj(intercept_step("llm_unavailable", round_i=round_i))
                yield sse(
                    "error",
                    {
                        "message": "模型连接暂时中断，正在基于已有结果收束…",
                        "recoverable": True,
                    },
                )
                async for chunk in _emit_think(
                    f"模型调用失败（已重试）：{str(exc)[:120]}。改为基于已有 Observation 收束答案…\n"
                ):
                    yield chunk
                    think_parts.append("llm_unavailable")
                content = await _answer_after_llm_failure(
                    model, task_ctx, round_i=round_i, run_state=run_state
                )
                citations = build_citations(task_ctx.facts)
                if citations:
                    yield sse("citations", {"items": citations})
                yield _emit_traj(finish_step(round_i=round_i))
                scratchpad.add_thought_action("模型不可用，材料收束", "finish", content, round_i)
                run_state.record_delivered(content)
                yield sse(
                    "react.finish",
                    {"round": round_i, "thought": "llm_unavailable", "content": content[:500]},
                )
                async for chunk in _emit_answer(content):
                    yield chunk
                assistant_parts = [content]
                break
        else:
            logger.info("resume react round=%s: %s", round_i, raw[:500])
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
            content = await _finalize_user_answer(
                model, task_ctx, content, round_i=round_i, thought=think, run_state=run_state
            )
            citations = build_citations(task_ctx.facts)
            if citations:
                yield sse("citations", {"items": citations})
            yield _emit_traj(finish_step(round_i=round_i))
            scratchpad.add_thought_action(think, "finish", content, round_i)
            run_state.record_delivered(content)
            yield sse("react.finish", {"round": round_i, "thought": think, "content": content[:500]})
            async for chunk in _emit_answer(content):
                yield chunk
            assistant_parts = [content]
            break

        if action == "tool":
            tool2 = str(parsed.get("tool") or "")
            args2 = parsed.get("args") if isinstance(parsed.get("args"), (dict, str)) else {}
            norm, verr = validate_and_normalize_args(tool2, args2)
            if verr:
                tip = f"工具参数无效: {verr}"
                scratchpad.add_thought_action(think, tool2, args2, round_i)
                scratchpad.set_observation(tip)
                yield sse("react.observation", {"round": round_i, "observation": tip, "tool": tool2})
                continue
            args2 = norm or {}
            if tool2 in CONFIRM_TOOLS:
                tip = "续跑中不再嵌套确认，请换只读工具或直接 finish。"
                scratchpad.add_thought_action(think, tool2, args2, round_i)
                scratchpad.set_observation(tip)
                yield sse("react.observation", {"round": round_i, "observation": tip})
                continue

            scratchpad.add_thought_action(think, tool2, args2, round_i)
            yield sse("react.action", {"round": round_i, "tool": tool2, "args": args2, "thought": think})
            yield _emit_traj(action_step(tool2, args2, round_i=round_i, status="running"))
            yield sse("tool.started", {"tool": tool2, "args": args2, "round": round_i})
            try:
                result2 = await execute_tool(
                    tool2, args2, db=db, user_id=user_id, conversation_id=conversation_id
                )
            except Exception as exc:
                result2 = {"error": str(exc)}
            if not isinstance(result2, dict):
                result2 = {"error": "bad result"}
            apply_result_to_context(task_ctx, tool2, result2, args=args2)
            if isinstance(result2, dict) and result2.get("frame"):
                yield sse("browser.frame", {"url": result2.get("url"), "frame": result2["frame"]})
            if isinstance(result2, dict) and result2.get("file_id"):
                item = {"file_id": result2["file_id"], "name": result2.get("name")}
                file_meta.append(item)
                yield sse("file.ready", item)
            obs2 = format_observation(tool2, result2)
            scratchpad.set_observation(obs2)
            yield _emit_traj(
                observation_step(tool2, round_i=round_i, ok=bool(task_ctx.last_ok), summary=obs2)
            )
            yield sse("react.observation", {"round": round_i, "observation": obs2, "tool": tool2})
            yield sse("tool.finished", {"tool": tool2, "result": _shrink(result2)})
            async for chunk in _emit_think(f"Observation: {obs2}\n"):
                yield chunk
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
    if not final_text or looks_like_internal(final_text):
        final_text = await _finalize_user_answer(
            model, task_ctx, final_text, round_i=agent_max_tool_rounds, run_state=run_state
        )
    final_text = enforce_safety_answer(goal=task_ctx.goal or "", answer=final_text)
    if task_ctx.artifacts and all(a not in final_text for a in task_ctx.artifacts):
        final_text = (
            final_text.rstrip()
            + "\n\n"
            + f"文件 {'、'.join(task_ctx.artifacts)} 已准备好，可点击下方下载。"
        )
    citations = build_citations(task_ctx.facts)
    if citations:
        yield sse("citations", {"items": citations})
    run_state.complete()
    _persist_run_state(db, user_id, conversation_id, run_id, run_state, milestone="resume_complete")
    db.add(
        Message(
            conversation_id=conversation_id,
            user_id=user_id,
            role="assistant",
            content=final_text,
            metadata_json=_build_assistant_metadata(
                run_id=run_id,
                think_parts=think_parts,
                scratchpad=scratchpad,
                trajectory_log=trajectory_log,
                task_ctx=task_ctx,
                run_state=run_state,
                file_meta=file_meta,
                citations=citations,
                extra={"resumed": True, "confirmation_id": confirmation_id},
            ),
        )
    )
    db.commit()
    yield sse("done", {"run_id": run_id, "finalize_path": run_state.finalize_path, "resumed": True})


# 保留旧名供路由兼容（若仍引用）
# resume_after_confirmation 已在上方定义
