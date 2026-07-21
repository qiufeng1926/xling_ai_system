"""五级历史关联调度（方案对齐）：意图 → 实体 → Task → 向量 → 权重排序 → 结构化注入。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from agent.entity_match import EntityMatchResult, match_entities
from agent.memory_policy import (
    classify_intent,
    is_dialog_followup,
    is_new_independent_question,
)
from agent.memory_scoring import MemoryCandidate, rank_candidates
from agent.session_memory import StructuredSummaryView, prepare_session_window
from agent.task_binding import ActiveTask
from utils.logger import get_logger

logger = get_logger("memory_pipeline")

SECONDARY_VALIDATION_RULES = (
    "规则（模型二次校验，强制）：\n"
    "1. 只使用与当前用户目标直接相关的候选；弱相关、错误匹配的条目必须忽略。\n"
    "2. 禁止把无关历史硬扯进回答；换题后禁止续写已关闭任务主题。\n"
    "3. 需要旧轮原文细节时，先 memory_recall(summary_id=…) 再作答。\n"
    "4. 实体命中（文件名/单据号）与同 TaskID 约束优先于模糊相似。"
)

MEMORY_DISCIPLINE_BLOCK = (
    "# 记忆纪律\n"
    "1. 独立新问题与上一轮硬隔离：禁止联想/提及上一轮书名、新闻或结论。\n"
    "2. 仅当用户明确追问/续作才使用最近同题上下文。\n"
    "3. finish 必须是用户可读终稿：总起 + 要点；禁止内部话术。\n"
    "4. 只读搜索/抓取无需用户确认；自行 web_fetch 后总结交付。\n"
    "5. 若系统注入了活动 TaskID，必须沿用该任务目标与约束。\n"
    "6. 若系统注入了实体精确匹配，必须优先使用命中项。\n"
    "7. 会话压缩摘要仅供线索；追问旧细节先 memory_recall。\n"
    "8. 历史关联候选已排序：只采用直接相关条目，禁止硬扯其余候选（二次校验）。"
)


@dataclass
class MemoryAssembly:
    intent: str
    entity_result: EntityMatchResult
    window_history: list[Any]
    system_memory_block: str
    ranked: list[MemoryCandidate] = field(default_factory=list)
    summary_views: list[StructuredSummaryView] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)

    @property
    def entity_hits(self) -> list[dict[str, Any]]:
        return [h.to_dict() for h in self.entity_result.hits[:6]]


def _summary_to_candidate(v: StructuredSummaryView, *, sem_sim: float = 1.0) -> MemoryCandidate:
    return MemoryCandidate(
        kind="summary",
        text=f"{v.core_need}；{v.key_data}".strip("；"),
        sem_sim=sem_sim,
        scene=v.scene or "",
        task_id=v.task_id or "",
        summary_id=v.summary_id,
        meta={
            "core_need": v.core_need,
            "key_data": v.key_data,
            "message_id_from": v.message_id_from,
            "message_id_to": v.message_id_to,
        },
    )


def _render_ranked_block(ranked: list[MemoryCandidate], *, task_block: str, entity_block: str) -> str:
    lines = ["# 历史关联候选（已按综合分排序，弱相关必须忽略）"]
    if task_block:
        # 任务块已含标题，缩进为候选条目
        for ln in task_block.splitlines():
            if ln.startswith("#"):
                continue
            if ln.strip():
                lines.append(ln if ln.startswith("-") else f"- [task] {ln.lstrip('- ').strip()}")
    if entity_block:
        for ln in entity_block.splitlines():
            if ln.startswith("#") or not ln.strip():
                continue
            if ln.strip().startswith("-"):
                lines.append(ln.replace("- ", "- [entity] ", 1) if "[entity]" not in ln else ln)
            else:
                lines.append(f"- [entity] {ln.strip()}")
    for c in ranked:
        if c.kind in {"task", "entity"}:
            continue
        label = c.kind
        head = f"- [{label} score={c.final_score:.2f}]"
        bits = [head]
        if c.summary_id:
            bits.append(f"id={c.summary_id[:8]}")
        if c.scene:
            bits.append(f"场景={c.scene}")
        if c.text:
            bits.append(c.text[:160])
        lines.append(" · ".join(bits) if len(bits) > 1 else head)
    lines.append(SECONDARY_VALIDATION_RULES)
    return "\n".join(lines)


async def assemble_memory_context(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    user_text: str,
    history: list[Any],
    active_task: ActiveTask,
    effective_goal: str = "",
) -> MemoryAssembly:
    """五级递进装配：返回窗口历史 + 统一记忆注入块。"""
    goal = (effective_goal or user_text or "").strip()
    intent = classify_intent(goal)

    # L2 实体
    entity_result = match_entities(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        user_text=user_text,
        task_artifacts=active_task.artifacts,
        history=history,
    )

    # 窗口 + 摘要列表
    window_history, _legacy_summary_block, summary_views = prepare_session_window(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        history=history,
        task_id=active_task.task_id,
    )

    candidates: list[MemoryCandidate] = []

    # L3 任务（始终高优先，不进 rank 截断丢弃——单独注入）
    task_block = active_task.render_injection()
    candidates.append(
        MemoryCandidate(
            kind="task",
            text=active_task.goal or "",
            sem_sim=1.0,
            scene=intent,
            task_id=active_task.task_id,
            entity_hit=False,
            meta={"bind_mode": active_task.bind_mode},
        )
    )

    # 实体候选
    entity_block = entity_result.render_injection()
    for h in entity_result.hits[:6]:
        candidates.append(
            MemoryCandidate(
                kind="entity",
                text=h.value,
                sem_sim=1.0,
                scene=h.kind,
                task_id=active_task.task_id,
                entity_hit=True,
                meta=h.to_dict(),
            )
        )

    # 摘要候选（字面 sem=1，后续向量命中会覆盖/追加）
    for v in summary_views:
        candidates.append(_summary_to_candidate(v, sem_sim=0.85))

    # L4 向量模糊（追问或非独立新题）
    fuzzy_ok = is_dialog_followup(user_text) or (not is_new_independent_question(user_text))
    vector_payloads: list[dict[str, Any]] = []
    if fuzzy_ok:
        try:
            from agent.vector_memory import (
                recall_user_memory_sync,
                vector_recall_session,
            )

            vhits = await vector_recall_session(
                user_id=user_id,
                conversation_id=conversation_id,
                query=goal,
            )
            for h in vhits:
                candidates.append(
                    MemoryCandidate(
                        kind="vector",
                        text=f"{h.core_need}；{h.key_data}".strip("；"),
                        sem_sim=float(h.score),
                        scene=h.scene or "",
                        task_id=h.task_id or "",
                        summary_id=h.summary_id,
                        meta=h.to_item(),
                    )
                )
                vector_payloads.append(h.to_item())

            # 工具分块等同会话检索（vector_recall 已含 tool_step）
            # 长期用户记忆
            um = recall_user_memory_sync(user_id=user_id, query=goal, limit=4)
            for it in um:
                candidates.append(
                    MemoryCandidate(
                        kind="long_term",
                        text=str(it.get("core_need") or it.get("raw_excerpt") or "")[:300],
                        sem_sim=float(it.get("score") or 0.7),
                        scene=str(it.get("scene") or "preference"),
                        meta=it,
                    )
                )
        except Exception:
            logger.exception("vector stage failed conv=%s", conversation_id)

    # L5 权重排序（保留 task/entity 展示，排序池含全部）
    ranked_pool = [c for c in candidates if c.kind not in {"task", "entity"}]
    ranked = rank_candidates(
        ranked_pool,
        intent=intent,
        active_task_id=active_task.task_id,
        top_k=None,
        drop_disallowed=True,
    )

    # 实体/任务始终出现在注入头部；ranked 跟在后面
    assoc_block = _render_ranked_block(ranked, task_block=task_block, entity_block=entity_block)
    system_memory_block = assoc_block + "\n\n" + MEMORY_DISCIPLINE_BLOCK

    debug = {
        "intent": intent,
        "entity_hits": len(entity_result.hits),
        "summaries": len(summary_views),
        "vector_hits": len(vector_payloads),
        "ranked": [
            {"kind": c.kind, "score": c.final_score, "id": (c.summary_id or "")[:8]}
            for c in ranked[:8]
        ],
        "fuzzy": fuzzy_ok,
    }
    return MemoryAssembly(
        intent=intent,
        entity_result=entity_result,
        window_history=window_history,
        system_memory_block=system_memory_block,
        ranked=ranked,
        summary_views=summary_views,
        debug=debug,
    )


def assemble_memory_context_sync(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    user_text: str,
    history: list[Any],
    active_task: ActiveTask,
    effective_goal: str = "",
) -> MemoryAssembly:
    """同步版（自测）：向量阶段用 lexical。"""
    goal = (effective_goal or user_text or "").strip()
    intent = classify_intent(goal)
    entity_result = match_entities(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        user_text=user_text,
        task_artifacts=active_task.artifacts,
        history=history,
    )
    window_history, _, summary_views = prepare_session_window(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        history=history,
        task_id=active_task.task_id,
    )
    candidates: list[MemoryCandidate] = [
        MemoryCandidate(
            kind="task",
            text=active_task.goal or "",
            sem_sim=1.0,
            scene=intent,
            task_id=active_task.task_id,
        )
    ]
    for h in entity_result.hits[:6]:
        candidates.append(
            MemoryCandidate(
                kind="entity",
                text=h.value,
                sem_sim=1.0,
                scene=h.kind,
                task_id=active_task.task_id,
                entity_hit=True,
                meta=h.to_dict(),
            )
        )
    for v in summary_views:
        candidates.append(_summary_to_candidate(v, sem_sim=0.85))

    fuzzy_ok = is_dialog_followup(user_text) or (not is_new_independent_question(user_text))
    if fuzzy_ok:
        try:
            from agent.vector_memory import (
                recall_user_memory_sync,
                vector_recall_session_sync,
            )

            for h in vector_recall_session_sync(
                user_id=user_id,
                conversation_id=conversation_id,
                query=goal,
                score_threshold=0.45,
            ):
                candidates.append(
                    MemoryCandidate(
                        kind="vector",
                        text=f"{h.core_need}；{h.key_data}".strip("；"),
                        sem_sim=float(h.score),
                        scene=h.scene or "",
                        task_id=h.task_id or "",
                        summary_id=h.summary_id,
                        meta=h.to_item(),
                    )
                )
            for it in recall_user_memory_sync(user_id=user_id, query=goal, limit=4):
                candidates.append(
                    MemoryCandidate(
                        kind="long_term",
                        text=str(it.get("core_need") or "")[:300],
                        sem_sim=float(it.get("score") or 0.7),
                        scene=str(it.get("scene") or "preference"),
                        meta=it,
                    )
                )
        except Exception:
            logger.exception("sync vector stage failed")

    ranked = rank_candidates(
        [c for c in candidates if c.kind not in {"task", "entity"}],
        intent=intent,
        active_task_id=active_task.task_id,
        drop_disallowed=True,
    )
    task_block = active_task.render_injection()
    entity_block = entity_result.render_injection()
    assoc = _render_ranked_block(ranked, task_block=task_block, entity_block=entity_block)
    return MemoryAssembly(
        intent=intent,
        entity_result=entity_result,
        window_history=window_history,
        system_memory_block=assoc + "\n\n" + MEMORY_DISCIPLINE_BLOCK,
        ranked=ranked,
        summary_views=summary_views,
        debug={"intent": intent, "ranked_n": len(ranked), "fuzzy": fuzzy_ok},
    )
