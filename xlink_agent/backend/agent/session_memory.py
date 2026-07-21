"""长会话结构化摘要与可逆召回（方案第三步）。

- 窗口外旧轮次压缩为「场景 + 核心需求 + 关键数据」
- 原文摘要落库，可用 memory_recall 按 summary_id / 关键词取回
- 实现 MemoryRecallPort，与实体匹配同一消费形状

不做向量检索（第四步）。
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from agent.entity_match import EntityHit, EntityMatchResult, MemoryRecallPort
from agent.memory_policy import classify_topics
from db.models import ConversationSummary, Message
from utils.logger import get_logger

logger = get_logger("session_memory")

# 保留最近若干「用户轮」完整进窗口；更早的做摘要（方案瞬时 ~5 轮）
DEFAULT_KEEP_USER_TURNS = 5
# 超过该用户轮数才触发压缩
COMPACT_TRIGGER_USER_TURNS = 7


def _keep_user_turns() -> int:
    try:
        from config.config import session_keep_user_turns

        return max(1, int(session_keep_user_turns))
    except Exception:
        return DEFAULT_KEEP_USER_TURNS


@dataclass
class StructuredSummaryView:
    summary_id: str
    scene: str
    core_need: str
    key_data: str
    task_id: str = ""
    message_id_from: int = 0
    message_id_to: int = 0

    def render_line(self) -> str:
        bits = [f"[{self.summary_id[:8]}]"]
        if self.scene:
            bits.append(f"场景={self.scene}")
        if self.core_need:
            bits.append(f"需求={self.core_need[:120]}")
        if self.key_data:
            bits.append(f"要点={self.key_data[:160]}")
        return " · ".join(bits)


def _msg_fields(item: Any) -> tuple[int, str, str, str]:
    mid = int(getattr(item, "id", None) or (item.get("id") if isinstance(item, dict) else 0) or 0)
    role = str(
        getattr(item, "role", None) or (item.get("role") if isinstance(item, dict) else "") or ""
    )
    content = str(
        getattr(item, "content", None)
        or (item.get("content") if isinstance(item, dict) else "")
        or ""
    )
    meta = getattr(item, "metadata_json", None) or (
        item.get("metadata_json") if isinstance(item, dict) else ""
    )
    return mid, role, content, str(meta or "")


def _covered_message_ids(db: Session, conversation_id: int, user_id: int) -> set[int]:
    rows = (
        db.query(ConversationSummary)
        .filter(
            ConversationSummary.conversation_id == conversation_id,
            ConversationSummary.user_id == user_id,
        )
        .all()
    )
    covered: set[int] = set()
    for r in rows:
        a, b = int(r.message_id_from or 0), int(r.message_id_to or 0)
        if a and b and b >= a:
            covered.update(range(a, b + 1))
    return covered


def _pair_turns(history: list[Any]) -> list[list[Any]]:
    """按用户消息切分为轮次：[user, assistant?, ... until next user)。"""
    turns: list[list[Any]] = []
    cur: list[Any] = []
    for item in history:
        _, role, _, _ = _msg_fields(item)
        if role == "user":
            if cur:
                turns.append(cur)
            cur = [item]
        elif role == "assistant":
            if not cur:
                continue
            cur.append(item)
    if cur:
        turns.append(cur)
    return turns


def _build_structured_from_turn(turn: list[Any], *, task_id: str = "") -> dict[str, str]:
    user_text = ""
    assistant_text = ""
    artifacts: list[str] = []
    mid_from = 0
    mid_to = 0
    for item in turn:
        mid, role, content, meta = _msg_fields(item)
        if mid:
            mid_from = mid if not mid_from else min(mid_from, mid)
            mid_to = max(mid_to, mid)
        if role == "user" and not user_text:
            user_text = content.strip()
        elif role == "assistant":
            assistant_text = content.strip()
            if meta:
                try:
                    import json

                    m = json.loads(meta)
                    for f in m.get("files") or []:
                        if isinstance(f, dict) and f.get("name"):
                            artifacts.append(str(f["name"]))
                    for a in (m.get("task_context") or {}).get("artifacts") or []:
                        if a:
                            artifacts.append(str(a))
                except Exception:
                    pass

    topics = classify_topics(user_text) | classify_topics(assistant_text)
    scene = "、".join(sorted(t for t in topics if t != "general")) or "general"
    core = re.sub(r"\s+", " ", user_text)[:240]
    ans = re.sub(r"\s+", " ", assistant_text)[:280]
    key_parts: list[str] = []
    if artifacts:
        key_parts.append("产物:" + "、".join(list(dict.fromkeys(artifacts))[:6]))
    if ans:
        key_parts.append("答复摘要:" + ans)
    key_data = "；".join(key_parts)[:500]
    raw_parts = []
    if user_text:
        raw_parts.append(f"用户: {user_text[:800]}")
    if assistant_text:
        raw_parts.append(f"助手: {assistant_text[:1200]}")
    return {
        "scene": scene,
        "core_need": core or "（空）",
        "key_data": key_data or "（无）",
        "raw_excerpt": "\n".join(raw_parts)[:3500],
        "task_id": task_id or "",
        "message_id_from": str(mid_from),
        "message_id_to": str(mid_to),
    }


def maybe_compact_conversation(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    history: list[Any],
    task_id: str = "",
    keep_user_turns: int | None = None,
    trigger_user_turns: int | None = None,
) -> list[ConversationSummary]:
    """若会话足够长，把窗口外未覆盖轮次写成结构化摘要。"""
    keep = _keep_user_turns() if keep_user_turns is None else keep_user_turns
    trigger = COMPACT_TRIGGER_USER_TURNS if trigger_user_turns is None else trigger_user_turns
    if trigger < keep + 1:
        trigger = keep + 2
    turns = _pair_turns(history)
    if len(turns) < trigger:
        return []

    covered = _covered_message_ids(db, conversation_id, user_id)
    # 保留最近 keep；压缩更早的
    to_compact = turns[:-keep] if keep > 0 else turns
    created: list[ConversationSummary] = []
    for turn in to_compact:
        ids = [_msg_fields(x)[0] for x in turn if _msg_fields(x)[0]]
        if not ids:
            continue
        if all(i in covered for i in ids):
            continue
        # 至少有一条未覆盖
        if any(i in covered for i in ids) and not any(i not in covered for i in ids):
            continue
        data = _build_structured_from_turn(turn, task_id=task_id)
        mid_from = int(data["message_id_from"] or 0)
        mid_to = int(data["message_id_to"] or 0)
        if not mid_from or not mid_to:
            continue
        row = ConversationSummary(
            summary_id=uuid.uuid4().hex,
            user_id=user_id,
            conversation_id=conversation_id,
            task_id=data.get("task_id") or task_id or "",
            message_id_from=mid_from,
            message_id_to=mid_to,
            scene=data["scene"],
            core_need=data["core_need"],
            key_data=data["key_data"],
            raw_excerpt=data["raw_excerpt"],
        )
        db.add(row)
        created.append(row)
        covered.update(range(mid_from, mid_to + 1))
    if created:
        db.commit()
        for r in created:
            db.refresh(r)
        logger.info(
            "compacted %s turns conv=%s uid=%s",
            len(created),
            conversation_id,
            user_id,
        )
    return created


def list_recent_summaries(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    task_id: str = "",
    limit: int = 6,
) -> list[StructuredSummaryView]:
    q = db.query(ConversationSummary).filter(
        ConversationSummary.user_id == user_id,
        ConversationSummary.conversation_id == conversation_id,
    )
    rows = q.order_by(ConversationSummary.created_at.desc()).limit(limit * 2).all()
    views: list[StructuredSummaryView] = []
    for r in rows:
        # 同任务优先：先收同 task，再补其它
        views.append(
            StructuredSummaryView(
                summary_id=r.summary_id,
                scene=r.scene or "",
                core_need=r.core_need or "",
                key_data=r.key_data or "",
                task_id=r.task_id or "",
                message_id_from=int(r.message_id_from or 0),
                message_id_to=int(r.message_id_to or 0),
            )
        )
    if task_id:
        same = [v for v in views if v.task_id == task_id]
        other = [v for v in views if v.task_id != task_id]
        views = (same + other)[:limit]
    else:
        views = views[:limit]
    return views


def render_summary_injection(views: list[StructuredSummaryView]) -> str:
    if not views:
        return ""
    lines = [
        "# 会话压缩摘要（窗口外历史，可逆；需要细节时用 memory_recall）",
    ]
    for v in views:
        lines.append(f"- {v.render_line()}")
    lines.append(
        "- 规则: 以上为精简摘要，不是完整原文；若用户追问旧细节，"
        "先 memory_recall(summary_id=…) 取回，再作答。"
    )
    return "\n".join(lines)


def recall_session_memory(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    summary_id: str = "",
    query: str = "",
    limit: int = 5,
    mode: str = "auto",
) -> dict[str, Any]:
    """按 summary_id 精确取回，或按关键词/向量模糊匹配。

    mode: auto | keyword | vector
    - auto: 先关键词，不足再用向量补齐
    - keyword: 仅字面
    - vector: 仅向量
    """
    sid = (summary_id or "").strip()
    q = (query or "").strip()
    mode_n = (mode or "auto").strip().lower()
    if sid:
        row = (
            db.query(ConversationSummary)
            .filter(
                ConversationSummary.summary_id == sid,
                ConversationSummary.user_id == user_id,
            )
            .first()
        )
        # 允许短前缀匹配
        if not row and len(sid) >= 8:
            row = (
                db.query(ConversationSummary)
                .filter(
                    ConversationSummary.user_id == user_id,
                    ConversationSummary.conversation_id == conversation_id,
                    ConversationSummary.summary_id.startswith(sid[:8]),
                )
                .first()
            )
        if not row:
            return {"ok": False, "error": f"未找到 summary_id={sid}"}
        return {
            "ok": True,
            "items": [
                {
                    "summary_id": row.summary_id,
                    "scene": row.scene,
                    "core_need": row.core_need,
                    "key_data": row.key_data,
                    "raw_excerpt": (row.raw_excerpt or "")[:3500],
                    "message_id_from": row.message_id_from,
                    "message_id_to": row.message_id_to,
                    "task_id": row.task_id,
                    "match": "exact",
                }
            ],
        }

    if not q:
        return {"ok": False, "error": "memory_recall 需要 summary_id 或 query"}

    items: list[dict[str, Any]] = []
    if mode_n in {"auto", "keyword"}:
        rows = (
            db.query(ConversationSummary)
            .filter(
                ConversationSummary.user_id == user_id,
                ConversationSummary.conversation_id == conversation_id,
            )
            .order_by(ConversationSummary.created_at.desc())
            .limit(40)
            .all()
        )
        qn = q.lower()
        scored: list[tuple[int, ConversationSummary]] = []
        for r in rows:
            blob = f"{r.scene}\n{r.core_need}\n{r.key_data}\n{r.raw_excerpt}".lower()
            score = 0
            if qn in blob:
                score += 5
            for tok in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_\-.]{3,}", q):
                if tok.lower() in blob:
                    score += 1
            if score:
                scored.append((score, r))
        scored.sort(key=lambda x: -x[0])
        for _, r in scored[:limit]:
            items.append(
                {
                    "summary_id": r.summary_id,
                    "scene": r.scene,
                    "core_need": r.core_need,
                    "key_data": r.key_data,
                    "raw_excerpt": (r.raw_excerpt or "")[:2000],
                    "message_id_from": r.message_id_from,
                    "message_id_to": r.message_id_to,
                    "task_id": r.task_id,
                    "match": "keyword",
                }
            )

    if mode_n == "vector" or (mode_n == "auto" and len(items) < limit):
        try:
            from agent.vector_memory import enrich_recall_with_vectors

            if mode_n == "vector":
                items = enrich_recall_with_vectors(
                    db,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    query=q,
                    existing_items=[],
                    limit=limit,
                )
            else:
                items = enrich_recall_with_vectors(
                    db,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    query=q,
                    existing_items=items,
                    limit=limit,
                )
        except Exception:
            logger.exception("vector recall failed conv=%s", conversation_id)

    return {"ok": True, "items": items, "query": q, "mode": mode_n}


class SessionSummaryRecall(MemoryRecallPort):
    """把会话摘要召回适配为 EntityMatchResult，便于统一注入。"""

    def __init__(self, db: Session) -> None:
        self._db = db

    def recall(
        self,
        *,
        user_id: int,
        conversation_id: int,
        query: str,
        limit: int = 8,
    ) -> EntityMatchResult:
        data = recall_session_memory(
            self._db,
            user_id=user_id,
            conversation_id=conversation_id,
            query=query,
            limit=limit,
        )
        hits: list[EntityHit] = []
        for i, it in enumerate(data.get("items") or []):
            hits.append(
                EntityHit(
                    kind="session_summary",
                    value=str(it.get("core_need") or it.get("summary_id") or "")[:120],
                    source="session_summary",
                    score=1.0 - i * 0.05,
                    meta=it,
                )
            )
        return EntityMatchResult(hits=hits, query_entities=[query] if query else [])


def filter_history_for_window(
    history: list[Any],
    *,
    covered_ids: set[int],
    keep_user_turns: int = DEFAULT_KEEP_USER_TURNS,
) -> list[Any]:
    """已摘要覆盖的旧轮次移出 prompt 窗口，仅保留最近 keep 轮完整原文。"""
    turns = _pair_turns(history)
    if len(turns) <= keep_user_turns or keep_user_turns < 0:
        return list(history)
    out: list[Any] = []
    older, recent = turns[:-keep_user_turns], turns[-keep_user_turns:]
    for turn in older:
        ids = [i for i in (_msg_fields(x)[0] for x in turn) if i]
        if ids and all(i in covered_ids for i in ids):
            continue
        out.extend(turn)
    for turn in recent:
        out.extend(turn)
    return out


def prepare_session_window(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    history: list[Any],
    task_id: str = "",
    keep_user_turns: int | None = None,
) -> tuple[list[Any], str, list[StructuredSummaryView]]:
    """组装：窗口内原文 + 摘要注入块。"""
    keep = _keep_user_turns() if keep_user_turns is None else keep_user_turns
    views = list_recent_summaries(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        task_id=task_id,
    )
    covered = _covered_message_ids(db, conversation_id, user_id)
    windowed = filter_history_for_window(
        history, covered_ids=covered, keep_user_turns=keep
    )
    return windowed, render_summary_injection(views), views


def restore_messages_for_summary(
    db: Session,
    *,
    user_id: int,
    summary_id: str,
) -> list[dict[str, str]]:
    """可逆：按摘要区间取回原消息（只读）。"""
    row = (
        db.query(ConversationSummary)
        .filter(
            ConversationSummary.summary_id == summary_id,
            ConversationSummary.user_id == user_id,
        )
        .first()
    )
    if not row:
        return []
    msgs = (
        db.query(Message)
        .filter(
            Message.conversation_id == row.conversation_id,
            Message.user_id == user_id,
            Message.id >= int(row.message_id_from or 0),
            Message.id <= int(row.message_id_to or 0),
        )
        .order_by(Message.id.asc())
        .all()
    )
    return [{"role": m.role, "content": (m.content or "")[:4000]} for m in msgs]
