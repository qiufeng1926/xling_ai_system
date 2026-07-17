"""Agent 运行状态机：追踪每步阶段、拦截原因与答案快照，便于排查归因。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RunPhase(str, Enum):
    INIT = "init"
    REASONING = "reasoning"
    INTERCEPT = "intercept"
    EXECUTING = "executing"
    OBSERVING = "observing"
    FINALIZING = "finalizing"
    DELIVERED = "delivered"
    AWAITING_CONFIRM = "awaiting_confirm"
    COMPLETE = "complete"
    FAILED = "failed"


class FinalizePath(str, Enum):
    DRAFT_DIRECT_NO_MATERIALS = "draft_direct_no_materials"
    DRAFT_EXPANDED = "draft_expanded"
    RICH_SYNTHESIS = "rich_synthesis"
    DRAFT_AFTER_RICH_FAIL = "draft_after_rich_fail"
    DRAFT_NON_HOLLOW = "draft_non_hollow"
    SUBSTANTIVE_BEFORE_FALLBACK = "substantive_before_fallback"
    KNOWLEDGE_FALLBACK = "knowledge_fallback"
    VERIFIED = "verified"
    SUBSTANTIVE_AFTER_VERIFY = "substantive_after_verify"
    ENTITY_SYNTHESIS = "entity_synthesis"
    ENTITY_LIST_RAW = "entity_list_raw"
    KNOWLEDGE_LAST_RESORT = "knowledge_last_resort"


@dataclass
class StateTransition:
    phase: RunPhase
    round_i: int = -1
    reason: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


@dataclass
class AnswerSnapshot:
    """某一步可交付/候选答案的快照。"""

    label: str
    text: str
    round_i: int = -1
    path: str = ""
    has_materials: bool = False
    fact_count: int = 0
    ts: float = field(default_factory=time.time)


@dataclass
class AgentRunState:
    run_id: str
    goal: str
    phase: RunPhase = RunPhase.INIT
    round_i: int = -1
    transitions: list[StateTransition] = field(default_factory=list)
    answer_snapshots: list[AnswerSnapshot] = field(default_factory=list)
    intercepts: list[dict[str, Any]] = field(default_factory=list)
    finalize_path: str = ""
    delivered_text: str = ""
    react_finish_draft: str = ""
    error: str = ""

    def transition(
        self,
        phase: RunPhase,
        *,
        round_i: int | None = None,
        reason: str = "",
        **detail: Any,
    ) -> None:
        if round_i is not None:
            self.round_i = round_i
        self.phase = phase
        self.transitions.append(
            StateTransition(
                phase=phase,
                round_i=self.round_i,
                reason=reason,
                detail=dict(detail),
            )
        )

    def begin_round(self, round_i: int) -> None:
        self.transition(RunPhase.REASONING, round_i=round_i, reason="llm_react")

    def intercept(self, reason: str, *, round_i: int | None = None, **detail: Any) -> None:
        entry = {
            "reason": reason,
            "round": round_i if round_i is not None else self.round_i,
            **detail,
        }
        self.intercepts.append(entry)
        self.transition(RunPhase.INTERCEPT, round_i=round_i, reason=reason, **detail)

    def record_react_parsed(
        self, *, round_i: int, action: str, tool: str = "", thought: str = ""
    ) -> None:
        self.transition(
            RunPhase.REASONING,
            round_i=round_i,
            reason="parsed",
            action=action,
            tool=tool,
            thought=(thought or "")[:200],
        )

    def record_tool_start(self, tool: str, args: dict[str, Any] | str) -> None:
        self.transition(
            RunPhase.EXECUTING,
            reason="tool_start",
            tool=tool,
            args_preview=str(args)[:300],
        )

    def record_tool_done(self, tool: str, ok: bool, summary: str = "") -> None:
        self.transition(
            RunPhase.OBSERVING,
            reason="tool_done",
            tool=tool,
            ok=ok,
            summary=(summary or "")[:400],
        )

    def snapshot_answer(
        self,
        label: str,
        text: str,
        *,
        round_i: int | None = None,
        path: str = "",
        has_materials: bool = False,
        fact_count: int = 0,
    ) -> None:
        self.answer_snapshots.append(
            AnswerSnapshot(
                label=label,
                text=(text or "")[:2000],
                round_i=round_i if round_i is not None else self.round_i,
                path=path,
                has_materials=has_materials,
                fact_count=fact_count,
            )
        )

    def record_finalize(
        self, path: FinalizePath | str, text: str, *, round_i: int | None = None
    ) -> None:
        p = path.value if isinstance(path, FinalizePath) else str(path)
        self.finalize_path = p
        self.transition(RunPhase.FINALIZING, round_i=round_i, reason=p)
        self.snapshot_answer("final", text, round_i=round_i, path=p)

    def record_delivered(self, text: str) -> None:
        self.delivered_text = (text or "")[:4000]
        self.transition(RunPhase.DELIVERED, reason="user_answer", len=len(self.delivered_text))
        self.snapshot_answer("delivered", text, path=self.finalize_path or "direct")

    def complete(self) -> None:
        self.transition(RunPhase.COMPLETE, reason="run_done")

    def fail(self, error: str) -> None:
        self.error = error[:500]
        self.transition(RunPhase.FAILED, reason=error[:200])

    def attribution_summary(self) -> str:
        """单行归因摘要，便于日志检索。"""
        last_snap = self.answer_snapshots[-1].label if self.answer_snapshots else "none"
        intercept_n = len(self.intercepts)
        return (
            f"phase={self.phase.value} rounds={self.round_i + 1} "
            f"finalize={self.finalize_path or '-'} intercepts={intercept_n} "
            f"last_snap={last_snap} facts_in_ctx={self._last_fact_count()}"
        )

    def _last_fact_count(self) -> int:
        for s in reversed(self.answer_snapshots):
            if s.fact_count:
                return s.fact_count
        return 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "goal": self.goal[:300],
            "phase": self.phase.value,
            "round_i": self.round_i,
            "finalize_path": self.finalize_path,
            "delivered_len": len(self.delivered_text),
            "react_finish_draft": self.react_finish_draft[:500],
            "intercepts": self.intercepts[-20:],
            "transitions": [
                {
                    "phase": t.phase.value,
                    "round": t.round_i,
                    "reason": t.reason,
                    "detail": {k: str(v)[:200] for k, v in t.detail.items()},
                }
                for t in self.transitions[-40:]
            ],
            "answer_snapshots": [
                {
                    "label": s.label,
                    "path": s.path,
                    "round": s.round_i,
                    "has_materials": s.has_materials,
                    "fact_count": s.fact_count,
                    "preview": s.text[:300],
                }
                for s in self.answer_snapshots[-12:]
            ],
            "error": self.error,
        }
