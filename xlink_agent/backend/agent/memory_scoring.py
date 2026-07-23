"""多维权重打分（方案 §3.5）。

综合得分 = 语义相似度 × 场景权重 × 时间衰减系数 × 任务绑定系数
（工程增强：实体字面命中再 × entity_boost）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from agent.memory_policy import classify_intent, intent_allows_candidate


def _cfg_float(name: str, default: float) -> float:
    try:
        from config import config as cfg

        return float(getattr(cfg, name, default))
    except Exception:
        return default


def _cfg_int(name: str, default: int) -> int:
    try:
        from config import config as cfg

        return int(getattr(cfg, name, default))
    except Exception:
        return default


@dataclass
class MemoryCandidate:
    """统一候选片段，供排序与注入。"""

    kind: str  # summary | vector | entity | tool_step | long_term | task
    text: str
    sem_sim: float = 1.0
    scene: str = ""
    task_id: str = ""
    summary_id: str = ""
    created_at: datetime | None = None
    entity_hit: bool = False
    meta: dict[str, Any] = field(default_factory=dict)
    final_score: float = 0.0

    def blob_for_filter(self) -> str:
        return f"{self.scene}\n{self.text}"


def scene_weight(intent: str, cand: MemoryCandidate) -> float:
    """场景权重：冲突压到 0.5；匹配或中性 1.0。"""
    if cand.kind in {"task", "entity"}:
        return 1.0
    if intent_allows_candidate(intent, scene=cand.scene, text=cand.text):
        # 闲聊类在严肃意图下即使放过也降权
        if intent not in {"chitchat", "general"} and classify_intent(cand.blob_for_filter()) == "chitchat":
            return _cfg_float("memory_weight_chitchat", 0.5)
        return 1.0
    return _cfg_float("memory_weight_chitchat", 0.5)


def time_decay(created_at: datetime | None, *, recent_turns_boost: bool = False) -> float:
    """时间衰减：近 3 轮/近窗 1.5；越旧越低，下限 0.5。"""
    if recent_turns_boost:
        return _cfg_float("memory_weight_recent", 1.5)
    if created_at is None:
        return 1.0
    now = datetime.now(timezone.utc)
    ts = created_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_hours = max(0.0, (now - ts).total_seconds() / 3600.0)
    if age_hours <= 6:
        return _cfg_float("memory_weight_recent", 1.5)
    if age_hours <= 48:
        return 1.0
    if age_hours <= 168:
        return 0.75
    return _cfg_float("memory_weight_chitchat", 0.5)


def task_bind_coef(cand: MemoryCandidate, active_task_id: str) -> float:
    if active_task_id and cand.task_id and cand.task_id == active_task_id:
        return _cfg_float("memory_weight_same_task", 2.0)
    if cand.kind == "long_term":
        return _cfg_float("memory_weight_long_term", 1.3)
    if cand.kind == "task":
        return _cfg_float("memory_weight_same_task", 2.0)
    return 1.0


def score_candidate(
    cand: MemoryCandidate,
    *,
    intent: str,
    active_task_id: str = "",
    recent: bool = False,
) -> float:
    sem = float(cand.sem_sim) if cand.sem_sim is not None else 1.0
    if cand.kind in {"entity", "task"}:
        sem = 1.0
    sem = max(0.0, min(sem, 1.0))
    sw = scene_weight(intent, cand)
    td = time_decay(cand.created_at, recent_turns_boost=recent)
    tb = task_bind_coef(cand, active_task_id)
    score = sem * sw * td * tb
    if cand.entity_hit:
        # 设计稿：实体命中系数 1.8
        score *= _cfg_float("memory_weight_entity_boost", 1.8)
    return round(score, 6)


def rank_candidates(
    candidates: list[MemoryCandidate],
    *,
    intent: str,
    active_task_id: str = "",
    recent_ids: set[str] | None = None,
    top_k: int | None = None,
    drop_disallowed: bool = True,
) -> list[MemoryCandidate]:
    """过滤冲突 → 打分 → 截断 Top3–8。"""
    recent_ids = recent_ids or set()
    k = top_k if top_k is not None else _cfg_int("session_memory_top_k", 6)
    k = max(3, min(8, int(k)))

    filtered: list[MemoryCandidate] = []
    for c in candidates:
        if drop_disallowed and c.kind not in {"task", "entity"}:
            if not intent_allows_candidate(intent, scene=c.scene, text=c.text):
                continue
        recent = False
        sid = c.summary_id or str(c.meta.get("id") or "")
        if sid and sid in recent_ids:
            recent = True
        elif c.kind in {"task", "entity"}:
            recent = True
        c.final_score = score_candidate(
            c, intent=intent, active_task_id=active_task_id, recent=recent
        )
        filtered.append(c)

    filtered.sort(key=lambda x: (-x.final_score, x.kind))
    return filtered[:k]
