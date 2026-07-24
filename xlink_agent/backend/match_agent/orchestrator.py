"""商单筛库专用 ReAct 编排（不经过通用 orchestrator / delivery / web 工具）。"""

from __future__ import annotations

import json
import re
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


def _parse_follower_min_from_brief(text: str) -> int | None:
    """从商单文本解析粉丝下限（通用，非垂类硬编码）。"""
    t = text or ""
    m = re.search(r"粉丝[量数]?\s*[≥>~＞]?\s*(\d+)\s*万", t)
    if m:
        return int(m.group(1)) * 10000
    m = re.search(r"(\d+)\s*万\s*(?:以上|粉丝)", t)
    if m:
        return int(m.group(1)) * 10000
    m = re.search(r"follower[_\s-]*min\s*[=:：]?\s*(\d+)", t, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"粉丝[量数]?\s*[≥>~＞]?\s*(\d{4,})", t)
    if m:
        return int(m.group(1))
    return None


def _extract_topic_keyword(text: str) -> str | None:
    """抽短主题词：去掉常见噪声后取 2～8 字片段，供 keyword 检索。"""
    t = re.sub(r"\s+", "", text or "")
    for noise in (
        "推广商单",
        "推销商单",
        "商单",
        "粉丝量",
        "粉丝数",
        "粉丝",
        "以上",
        "需要",
        "要是",
        "偏",
        "风格",
        "高质量",
        "请",
        "筛选",
        "达人",
        "博主",
    ):
        t = t.replace(noise, " ")
    t = re.sub(r"\d+万?", " ", t)
    parts = [p for p in re.split(r"[\s,，、/|]+", t) if len(p) >= 2]
    if not parts:
        return None
    # 取最短有意义片段，避免整句
    parts.sort(key=len)
    return parts[0][:8]


async def _fallback_catalog_search(user_text: str) -> dict[str, Any]:
    """模型空转时的通用兜底检索：粉丝下限 + 短 keyword。"""
    from tools.influencer_tools import influencer_search

    args: dict[str, Any] = {"page_size": 30}
    fmin = _parse_follower_min_from_brief(user_text)
    if fmin:
        args["follower_min"] = fmin
    kw = _extract_topic_keyword(user_text)
    if kw:
        args["keyword"] = kw
    return await influencer_search(args)


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
                if not catalog and round_i < max_rounds - 1:
                    # 空库禁止早退：强制进入放宽检索
                    reject = {
                        "ok": False,
                        "error": (
                            "当前 Observation 中尚无达人记录，禁止 finish。"
                            "请先 influencer_list_tags，再用 follower_min + 短 keyword"
                            "（或真实 tag_ids）调用 influencer_search；"
                            "platform 只能是 douyin 或 xiaohongshu 单值。"
                        ),
                    }
                    scratchpad.add_thought_action(thought, "finish", action_input, round_i)
                    scratchpad.set_observation(observation_preview(reject))
                    yield sse(
                        "trajectory.step",
                        observation_step(
                            "finish",
                            round_i=round_i,
                            ok=False,
                            summary="empty_catalog_reject_finish",
                            reason="empty_catalog",
                        ),
                    )
                    continue
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
            # 勿把完整 Observation 推给前端：体积过大易拖垮 SSE / 代理断连
            yield sse(
                "tool.finished",
                {
                    "tool": action,
                    "ok": ok,
                    "summary": summary[:300],
                    "count": (result.get("count") if isinstance(result, dict) else None),
                },
            )
            yield sse("trajectory.step", done)

        else:
            final_text = build_grounded_answer(
                catalog,
                brief=user_text,
                ranked_ids=last_rank_ids or None,
            )

        # 模型空转兜底：仍无 catalog 时做一次通用放宽检索（非垂类硬编码）
        rebuilt_after_fallback = False
        if not catalog:
            fb = await _fallback_catalog_search(user_text)
            ingest_observation_catalog(catalog, fb)
            trajectory.append(
                observation_step(
                    "influencer_search",
                    round_i=max_rounds,
                    ok=bool(fb.get("ok")),
                    summary=f"fallback count={fb.get('count', 0)}",
                    reason="empty_catalog_fallback",
                )
            )
            yield sse("trajectory.step", trajectory[-1])
            rebuilt_after_fallback = True

        if not final_text or rebuilt_after_fallback:
            final_text = build_grounded_answer(
                catalog,
                brief=user_text,
                ranked_ids=last_rank_ids or None,
            )

        cards = build_influencer_cards(catalog, ranked_ids=last_rank_ids or None)

        # 先落库再推 SSE：客户端/代理提前断连时，历史仍可回看结果
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

        yield sse("think.close", {})
        for chunk in _emit_answer_chunks(final_text):
            yield chunk
        if cards:
            yield sse("match.cards", {"items": cards, "count": len(cards)})
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
