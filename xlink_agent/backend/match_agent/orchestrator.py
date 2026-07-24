"""商单筛库专用 ReAct 编排（不经过通用 orchestrator / delivery / web 工具）。"""

from __future__ import annotations

import json
import uuid
from typing import Any, AsyncIterator

from sqlalchemy.orm import Session

from agent.events import sse
from agent.model_router import LLMCallError, get_chat_model
from agent.react import ReactScratchpad, parse_react_output
from agent.trajectory import action_step, finish_step, observation_step
from config.config import agent_max_tool_rounds
from db.models import Conversation, Message
from match_agent import MATCH_KNOWN_TOOLS, MATCH_SKILL_SLUG, MATCH_SYSTEM_PROMPT, MATCH_TOOLS
from match_agent.grounding import (
    build_grounded_answer,
    build_influencer_cards,
    extract_ranked_ids_from_last_rank,
    ingest_observation_catalog,
    observation_preview,
)
from tools.influencer_tools import INFLUENCER_TOOL_HANDLERS
from tools.portal_context import get_portal_bearer
from tools.web_tools import render_tool_contracts, validate_and_normalize_args
from utils.logger import get_logger

logger = get_logger("match_agent")


def _contracts() -> str:
    return render_tool_contracts(MATCH_TOOLS)


def _system() -> str:
    return (
        MATCH_SYSTEM_PROMPT
        + "\n\n"
        + f"可用工具: {json.dumps(MATCH_TOOLS, ensure_ascii=False)}\n"
        + _contracts()
    )


async def _run_match_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name not in INFLUENCER_TOOL_HANDLERS:
        return {"ok": False, "error": f"商单筛库禁止调用工具: {name}"}
    if not get_portal_bearer():
        return {"ok": False, "error": "缺少门户登录令牌，无法读取达人库"}
    normalized, err = validate_and_normalize_args(name, args)
    if err:
        return {"ok": False, "error": err}
    handler = INFLUENCER_TOOL_HANDLERS[name]
    return await handler(normalized or {})


def _emit_answer_chunks(text: str) -> list[str]:
    out: list[str] = []
    step = 24
    for i in range(0, len(text), step):
        out.append(sse("message.delta", {"content": text[i : i + step]}))
    return out


async def run_match_chat(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    user_text: str,
) -> AsyncIterator[str]:
    """SSE：专用筛库对话。"""
    run_id = uuid.uuid4().hex
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user_id:
        yield sse("error", {"message": "会话不存在"})
        yield sse("done", {"ok": False})
        return
    if (conv.skill_slug or "") != MATCH_SKILL_SLUG:
        yield sse("error", {"message": "非商单筛库会话，请从商单筛库页创建"})
        yield sse("done", {"ok": False})
        return

    db.add(
        Message(
            conversation_id=conversation_id,
            user_id=user_id,
            role="user",
            content=user_text,
        )
    )
    db.commit()

    yield sse("run.started", {"run_id": run_id, "mode": "influencer-match"})
    yield sse("think.open", {"title": "商单筛库 ReAct"})

    history = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.id.asc())
        .all()
    )
    dialog: list[dict[str, str]] = [{"role": "system", "content": _system()}]
    for m in history[-12:]:
        if m.role in {"user", "assistant"} and (m.content or "").strip():
            dialog.append({"role": m.role, "content": m.content.strip()[:8000]})

    model = get_chat_model()
    scratchpad = ReactScratchpad()
    catalog: dict[int, dict[str, Any]] = {}
    last_rank_ids: list[int] = []
    trajectory: list[dict[str, Any]] = []
    final_text = ""

    max_rounds = max(4, min(int(agent_max_tool_rounds or 12), 16))

    try:
        for round_i in range(max_rounds):
            messages = list(dialog)
            if scratchpad.steps:
                messages.append(
                    {
                        "role": "user",
                        "content": scratchpad.render(max_steps=12)
                        + "\n\n请基于 Observation 继续；材料足够则 finish。"
                        "禁止网页搜索；终稿字段必须来自库记录。",
                    }
                )
            try:
                raw = await model.chat(messages, temperature=0.1)
            except LLMCallError as exc:
                yield sse("error", {"message": str(exc)})
                break

            parsed = parse_react_output(raw or "", MATCH_TOOLS, MATCH_KNOWN_TOOLS)
            thought = str(parsed.get("thought") or "")
            action = str(parsed.get("action") or "").strip()
            action_input = parsed.get("action_input")

            if thought:
                yield sse("think.delta", {"content": thought + "\n"})

            if action.lower() in {"finish", "final", "answer", "done"}:
                draft = action_input if isinstance(action_input, str) else json.dumps(
                    action_input, ensure_ascii=False
                )
                final_text = build_grounded_answer(
                    catalog,
                    brief=user_text,
                    ranked_ids=last_rank_ids or None,
                    draft=str(draft or ""),
                )
                step = finish_step(round_i=round_i, detail=f"库内候选 {len(catalog)} 人")
                trajectory.append(step)
                yield sse("trajectory.step", step)
                break

            if action not in MATCH_TOOLS:
                obs = {
                    "ok": False,
                    "error": f"不允许的工具: {action}。只能使用 {MATCH_TOOLS}",
                }
                scratchpad.add_thought_action(thought, action or "invalid", action_input, round_i)
                scratchpad.set_observation(observation_preview(obs))
                yield sse(
                    "trajectory.step",
                    observation_step(
                        action or "invalid",
                        round_i=round_i,
                        ok=False,
                        summary=str(obs.get("error") or ""),
                        reason="forbidden_tool",
                    ),
                )
                continue

            args = action_input if isinstance(action_input, dict) else {}
            yield sse("tool.started", {"tool": action, "args": args, "round": round_i})
            start = action_step(action, args, round_i=round_i, status="running")
            trajectory.append(start)
            yield sse("trajectory.step", start)

            result = await _run_match_tool(action, args)
            ingest_observation_catalog(catalog, result)
            if action == "influencer_rank":
                ids = extract_ranked_ids_from_last_rank(result)
                if ids:
                    last_rank_ids = ids

            scratchpad.add_thought_action(thought, action, args, round_i)
            scratchpad.set_observation(observation_preview(result))
            ok = bool(isinstance(result, dict) and result.get("ok", True) and not result.get("error"))
            summary = ""
            if isinstance(result, dict):
                if result.get("error"):
                    summary = str(result.get("error"))
                else:
                    summary = f"count={result.get('count', result.get('total', ''))}"
            done = observation_step(
                action,
                round_i=round_i,
                ok=ok,
                summary=summary,
                reason="" if ok else summary,
            )
            trajectory.append(done)
            yield sse("tool.finished", {"tool": action, "result": result})
            yield sse("trajectory.step", done)

        else:
            final_text = build_grounded_answer(
                catalog,
                brief=user_text,
                ranked_ids=last_rank_ids or None,
            )

        if not final_text:
            final_text = build_grounded_answer(catalog, brief=user_text)

        cards = build_influencer_cards(catalog, ranked_ids=last_rank_ids or None)

        yield sse("think.close", {})
        for chunk in _emit_answer_chunks(final_text):
            yield chunk
        if cards:
            yield sse("match.cards", {"items": cards, "count": len(cards)})

        db.add(
            Message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="assistant",
                content=final_text,
                metadata_json=json.dumps(
                    {
                        "run_id": run_id,
                        "mode": MATCH_SKILL_SLUG,
                        "trajectory": trajectory[-20:],
                        "catalog_ids": [c.get("id") for c in cards],
                        "influencers": cards,
                    },
                    ensure_ascii=False,
                ),
            )
        )
        db.commit()
        yield sse(
            "done",
            {"ok": True, "run_id": run_id, "count": len(cards), "influencers": cards},
        )
    except Exception as exc:
        logger.exception("match chat failed")
        yield sse("error", {"message": str(exc)})
        yield sse("done", {"ok": False})


async def run_match_oneshot(
    db: Session,
    *,
    user_id: int,
    brief: str,
    title: str = "通用智能体调用-商单筛库",
) -> dict[str, Any]:
    """供通用 xlink-agent 单向调用：内部跑一轮筛库，返回 grounded 结果。"""
    conv = Conversation(
        user_id=user_id,
        title=(title or "商单筛库")[:200],
        skill_slug=MATCH_SKILL_SLUG,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)

    answer_parts: list[str] = []
    meta: dict[str, Any] = {}
    async for chunk in run_match_chat(
        db, user_id=user_id, conversation_id=int(conv.id), user_text=brief
    ):
        # chunk 形如: event: xxx\ndata: {...}\n\n
        if "event: message.delta" in chunk:
            try:
                data_line = [ln for ln in chunk.split("\n") if ln.startswith("data:")][0]
                payload = json.loads(data_line[5:].strip())
                answer_parts.append(str(payload.get("content") or ""))
            except Exception:
                pass
        if "event: done" in chunk:
            try:
                data_line = [ln for ln in chunk.split("\n") if ln.startswith("data:")][0]
                meta = json.loads(data_line[5:].strip())
            except Exception:
                pass

    answer = "".join(answer_parts).strip()
    return {
        "ok": bool(meta.get("ok", True)) and bool(answer),
        "conversation_id": conv.id,
        "answer": answer,
        "count": meta.get("count"),
        "note": "结果仅来自达人库；商单筛库智能体不会搜索网页，也不会回调通用智能体。",
    }
