"""记忆与历史检索：任务绑定 > 实体 > 向量 > 长期记忆。

综合得分 = 语义分 × 任务系数(同任务 2.0) × 实体系数(命中 1.8) × 时间衰减
（实现委托 memory_pipeline + memory_scoring，保证与现网行为一致。）
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from agent.dispatch.types import MemoryHit, TaskTransition
from agent.memory_pipeline import MemoryAssembly, assemble_memory_context
from agent.memory_service import build_memory_context
from agent.memory_policy import filter_long_term_memory_lines
from agent.task_binding import ActiveTask


class MemoryRetriever:
    """设计稿 §3.3：多策略分级检索，强制 userId+sessionId 隔离。"""

    async def retrieve(
        self,
        db: Session,
        *,
        user_id: int,
        session_id: int,
        user_text: str,
        history: list[Any],
        active_task: ActiveTask,
        effective_goal: str,
        transition: TaskTransition | None = None,
    ) -> tuple[MemoryAssembly, list[MemoryHit], str]:
        # 闲聊：仍召回，但下游 ContextManager 会更严截断
        asm = await assemble_memory_context(
            db,
            user_id=user_id,
            conversation_id=session_id,
            user_text=user_text,
            history=history,
            active_task=active_task,
            effective_goal=effective_goal,
        )
        hits = self._to_hits(asm, active_task_id=active_task.task_id or "")
        # 长期记忆：SQL 画像行，按目标过滤后少量注入
        long_term_raw = build_memory_context(db, user_id)
        long_term = filter_long_term_memory_lines(long_term_raw, effective_goal)
        if long_term:
            hits.append(
                MemoryHit(
                    text=long_term[:800],
                    score=0.5,
                    source="long_term",
                    task_id="",
                )
            )
        if transition == TaskTransition.CHITCHAT:
            hits = [h for h in hits if h.source in {"task_bind", "entity", "long_term"}][:4]
        return asm, hits, long_term

    @staticmethod
    def _to_hits(asm: MemoryAssembly, *, active_task_id: str) -> list[MemoryHit]:
        out: list[MemoryHit] = []
        for c in asm.ranked or []:
            kind = c.kind or "vector"
            if kind == "task":
                source = "task_bind"
            elif kind == "entity":
                source = "entity"
            elif kind == "long_term":
                source = "long_term"
            elif kind == "summary":
                source = "summary"
            else:
                source = "vector"
            text = (c.text or "")[:400]
            if not text:
                continue
            out.append(
                MemoryHit(
                    text=text,
                    score=float(c.final_score or 0.0),
                    source=source,
                    task_id=c.task_id or active_task_id,
                    summary_id=c.summary_id or "",
                    meta={"kind": kind, "scene": c.scene or ""},
                )
            )
        # 去重：文本前缀
        seen: set[str] = set()
        uniq: list[MemoryHit] = []
        for h in sorted(out, key=lambda x: x.score, reverse=True):
            key = h.text[:80]
            if key in seen:
                continue
            seen.add(key)
            uniq.append(h)
        return uniq[:8]
