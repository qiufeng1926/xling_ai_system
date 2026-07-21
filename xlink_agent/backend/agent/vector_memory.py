"""会话向量记忆（方案第四步：模糊召回）。

- 压缩摘要写入独立 Qdrant collection（失败则进程内降级存储）
- 关键词未命中时按余弦相似度召回；阈值可配置
- 实现 MemoryRecallPort，与实体/摘要同一消费形状

不做完整权重中台或跨用户检索。
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.orm import Session

from agent.entity_match import EntityHit, EntityMatchResult, MemoryRecallPort
from db.models import ConversationSummary
from utils.logger import get_logger

logger = get_logger("vector_memory")

# 进程内降级：Qdrant 不可用时仍可测/可跑
_LOCAL_POINTS: dict[str, list[dict[str, Any]]] = {}


def lexical_embed(text: str, dim: int = 64) -> list[float]:
    """无 Embedding API 时的确定性降级向量（与 EchoChatModel 同思路）。"""
    import zlib

    vec = [0.0] * dim
    t = text or ""
    for i, ch in enumerate(t[: max(dim * 4, 64)]):
        vec[i % dim] += (ord(ch) % 97) / 97.0
    # 轻量 n-gram 加强语义区分（用 zlib 保证跨进程确定性，避免内置 hash 随机盐）
    for m in re.findall(r"[\u4e00-\u9fff]{2,4}|[A-Za-z0-9]{3,}", t.lower()):
        h = zlib.adler32(m.encode("utf-8")) % dim
        vec[h] += 0.35
    n = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / n for x in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return float(dot / (na * nb))


def _session_collection() -> str:
    try:
        from config.config import qdrant_session_collection

        return qdrant_session_collection
    except Exception:
        return "session_memory"


def _score_threshold() -> float:
    try:
        from config.config import session_memory_score_threshold

        return float(session_memory_score_threshold)
    except Exception:
        return 0.65


def _top_k_default() -> int:
    try:
        from config.config import session_memory_top_k

        return max(3, min(8, int(session_memory_top_k)))
    except Exception:
        return 6


def _user_memory_collection() -> str:
    try:
        from config.config import qdrant_user_memory_collection

        return qdrant_user_memory_collection
    except Exception:
        return "user_memory"


def _summary_point_id(summary_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"session_summary:{summary_id}"))


def _summary_embed_text(row: ConversationSummary | dict[str, Any]) -> str:
    if isinstance(row, dict):
        scene = row.get("scene") or ""
        core = row.get("core_need") or ""
        key = row.get("key_data") or ""
        raw = row.get("raw_excerpt") or ""
        sid = row.get("summary_id") or ""
    else:
        scene = row.scene or ""
        core = row.core_need or ""
        key = row.key_data or ""
        raw = row.raw_excerpt or ""
        sid = row.summary_id or ""
    return f"场景:{scene}\n需求:{core}\n要点:{key}\n原文:{raw[:1200]}\nid:{sid}"


def _payload_from_row(row: ConversationSummary) -> dict[str, Any]:
    return {
        "kind": "session_summary",
        "summary_id": row.summary_id,
        "user_id": int(row.user_id),
        "conversation_id": int(row.conversation_id),
        "task_id": row.task_id or "",
        "scene": row.scene or "",
        "core_need": (row.core_need or "")[:240],
        "key_data": (row.key_data or "")[:300],
        "raw_excerpt": (row.raw_excerpt or "")[:1500],
        "text": _summary_embed_text(row)[:2000],
    }


def _upsert_local(collection: str, points: list[dict[str, Any]]) -> None:
    store = _LOCAL_POINTS.setdefault(collection, [])
    by_id = {p["id"]: i for i, p in enumerate(store)}
    for p in points:
        if p["id"] in by_id:
            store[by_id[p["id"]]] = p
        else:
            store.append(p)


def _search_local(
    collection: str,
    vector: list[float],
    *,
    user_id: int,
    conversation_id: int,
    top_k: int,
    score_threshold: float,
) -> list[dict[str, Any]]:
    store = _LOCAL_POINTS.get(collection) or []
    scored: list[tuple[float, dict[str, Any]]] = []
    for p in store:
        pl = p.get("payload") or {}
        if int(pl.get("user_id") or 0) != int(user_id):
            continue
        if int(pl.get("conversation_id") or 0) != int(conversation_id):
            continue
        score = _cosine(vector, p.get("vector") or [])
        if score >= score_threshold:
            scored.append((score, pl))
    scored.sort(key=lambda x: -x[0])
    out = []
    for score, pl in scored[:top_k]:
        item = dict(pl)
        item["score"] = round(score, 4)
        out.append(item)
    return out


def upsert_session_vectors(points: list[dict[str, Any]], vector_size: int) -> bool:
    """写入会话向量：优先 Qdrant，失败降级本地。"""
    if not points:
        return True
    collection = _session_collection()
    try:
        from rag.qdrant_client import upsert_chunks

        ok = upsert_chunks(points, vector_size, collection=collection)
        if ok:
            return True
    except Exception as exc:
        logger.warning("session vector qdrant upsert failed: %s", exc)
    _upsert_local(collection, points)
    logger.info("session vectors stored locally n=%s collection=%s", len(points), collection)
    return True


def search_session_vectors(
    vector: list[float],
    *,
    user_id: int,
    conversation_id: int,
    top_k: int | None = None,
    score_threshold: float | None = None,
    kinds: list[str] | None = None,
) -> list[dict[str, Any]]:
    top_k = top_k if top_k is not None else _top_k_default()
    thr = score_threshold if score_threshold is not None else _score_threshold()
    collection = _session_collection()
    allowed = set(kinds or ["session_summary", "tool_step"])
    try:
        from rag.qdrant_client import search_vectors_filtered

        hits = search_vectors_filtered(
            vector,
            collection=collection,
            must=[
                ("user_id", user_id),
                ("conversation_id", conversation_id),
            ],
            top_k=max(top_k * 2, top_k),
            score_threshold=thr,
        )
        hits = [h for h in hits if str(h.get("kind") or "session_summary") in allowed]
        if hits:
            return hits[:top_k]
    except Exception as exc:
        logger.warning("session vector qdrant search failed: %s", exc)
    local = _search_local(
        collection,
        vector,
        user_id=user_id,
        conversation_id=conversation_id,
        top_k=max(top_k * 2, top_k),
        score_threshold=thr,
    )
    local = [h for h in local if str(h.get("kind") or "session_summary") in allowed]
    return local[:top_k]


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    try:
        from agent.model_router import get_chat_model

        model = get_chat_model()
        vecs = await model.embed(texts)
        if vecs and len(vecs) == len(texts):
            return vecs
    except Exception as exc:
        logger.warning("embed failed, lexical fallback: %s", exc)
    return [lexical_embed(t) for t in texts]


async def index_conversation_summaries(rows: list[ConversationSummary]) -> int:
    """把新摘要写入向量库。返回成功条数。"""
    if not rows:
        return 0
    texts = [_summary_embed_text(r) for r in rows]
    vectors = await embed_texts(texts)
    dim = len(vectors[0]) if vectors else 64
    points = []
    for row, vec in zip(rows, vectors):
        points.append(
            {
                "id": _summary_point_id(row.summary_id),
                "vector": vec,
                "payload": _payload_from_row(row),
            }
        )
    upsert_session_vectors(points, dim)
    return len(points)


def index_conversation_summaries_sync(
    rows: list[ConversationSummary],
    *,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> int:
    """同步索引（自测 / 无事件循环）。默认 lexical_embed。"""
    if not rows:
        return 0
    texts = [_summary_embed_text(r) for r in rows]
    if embed_fn:
        vectors = embed_fn(texts)
    else:
        vectors = [lexical_embed(t) for t in texts]
    dim = len(vectors[0]) if vectors else 64
    points = [
        {
            "id": _summary_point_id(row.summary_id),
            "vector": vec,
            "payload": _payload_from_row(row),
        }
        for row, vec in zip(rows, vectors)
    ]
    upsert_session_vectors(points, dim)
    return len(points)


@dataclass
class VectorHitView:
    summary_id: str
    score: float
    scene: str = ""
    core_need: str = ""
    key_data: str = ""
    raw_excerpt: str = ""
    task_id: str = ""

    def to_item(self) -> dict[str, Any]:
        return {
            "summary_id": self.summary_id,
            "scene": self.scene,
            "core_need": self.core_need,
            "key_data": self.key_data,
            "raw_excerpt": self.raw_excerpt,
            "task_id": self.task_id,
            "score": self.score,
            "match": "vector",
        }


def hits_from_payloads(payloads: list[dict[str, Any]]) -> list[VectorHitView]:
    out: list[VectorHitView] = []
    for p in payloads:
        sid = str(p.get("summary_id") or "")
        if not sid:
            continue
        out.append(
            VectorHitView(
                summary_id=sid,
                score=float(p.get("score") or 0),
                scene=str(p.get("scene") or ""),
                core_need=str(p.get("core_need") or ""),
                key_data=str(p.get("key_data") or ""),
                raw_excerpt=str(p.get("raw_excerpt") or "")[:2000],
                task_id=str(p.get("task_id") or ""),
            )
        )
    return out


async def vector_recall_session(
    *,
    user_id: int,
    conversation_id: int,
    query: str,
    limit: int | None = None,
    score_threshold: float | None = None,
) -> list[VectorHitView]:
    q = (query or "").strip()
    if not q:
        return []
    vec = (await embed_texts([q]))[0]
    payloads = search_session_vectors(
        vec,
        user_id=user_id,
        conversation_id=conversation_id,
        top_k=limit or _top_k_default(),
        score_threshold=score_threshold,
    )
    return hits_from_payloads(payloads)


def vector_recall_session_sync(
    *,
    user_id: int,
    conversation_id: int,
    query: str,
    limit: int | None = None,
    score_threshold: float | None = None,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> list[VectorHitView]:
    q = (query or "").strip()
    if not q:
        return []
    if embed_fn:
        vec = embed_fn([q])[0]
    else:
        vec = lexical_embed(q)
    payloads = search_session_vectors(
        vec,
        user_id=user_id,
        conversation_id=conversation_id,
        top_k=limit or _top_k_default(),
        score_threshold=score_threshold,
    )
    return hits_from_payloads(payloads)


def render_vector_injection(hits: list[VectorHitView]) -> str:
    if not hits:
        return ""
    lines = ["# 向量模糊召回（语义相似历史，已过滤低分）"]
    for h in hits[:6]:
        bits = [f"[{h.summary_id[:8]}]", f"score={h.score:.2f}"]
        if h.core_need:
            bits.append(f"需求={h.core_need[:100]}")
        if h.key_data:
            bits.append(f"要点={h.key_data[:120]}")
        lines.append("- " + " · ".join(bits))
    lines.append(
        "- 规则: 仅当与当前追问相关时使用；无关条目禁止硬扯。"
        "需要原文细节时 memory_recall(summary_id=…)。"
    )
    return "\n".join(lines)


def enrich_recall_with_vectors(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    query: str,
    existing_items: list[dict[str, Any]],
    limit: int = 5,
) -> list[dict[str, Any]]:
    """关键词结果不足时用向量补齐（同步 lexical/已索引向量）。"""
    if len(existing_items) >= limit:
        return existing_items
    seen = {str(it.get("summary_id") or "") for it in existing_items}
    # 若本地/Qdrant 尚无点，先把库内摘要补索引（lexical）
    _ensure_indexed_from_db(db, user_id=user_id, conversation_id=conversation_id)
    thr = _score_threshold()
    vhits = vector_recall_session_sync(
        user_id=user_id,
        conversation_id=conversation_id,
        query=query,
        limit=limit,
        score_threshold=thr,
    )
    # 关键词完全未命中时放宽一档：正式阈值下不低于 0.45；
    # 无 Qdrant（lexical 降级）再允许 0.35，避免开发环境失忆。
    if not vhits and not existing_items:
        loose = max(0.45, min(float(thr), 0.50))
        if loose < thr:
            vhits = vector_recall_session_sync(
                user_id=user_id,
                conversation_id=conversation_id,
                query=query,
                limit=limit,
                score_threshold=loose,
            )
        if not vhits:
            try:
                from rag.qdrant_client import get_qdrant

                qdrant_ok = get_qdrant() is not None
            except Exception:
                qdrant_ok = False
            if not qdrant_ok:
                vhits = vector_recall_session_sync(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    query=query,
                    limit=limit,
                    score_threshold=0.35,
                )
    out = list(existing_items)
    for h in vhits:
        if h.summary_id in seen:
            continue
        # 用 DB 补全更长 raw_excerpt
        row = (
            db.query(ConversationSummary)
            .filter(
                ConversationSummary.summary_id == h.summary_id,
                ConversationSummary.user_id == user_id,
            )
            .first()
        )
        if row:
            item = {
                "summary_id": row.summary_id,
                "scene": row.scene,
                "core_need": row.core_need,
                "key_data": row.key_data,
                "raw_excerpt": (row.raw_excerpt or "")[:2000],
                "message_id_from": row.message_id_from,
                "message_id_to": row.message_id_to,
                "task_id": row.task_id,
                "score": h.score,
                "match": "vector",
            }
        else:
            item = h.to_item()
        out.append(item)
        seen.add(h.summary_id)
        if len(out) >= limit:
            break
    return out


def _ensure_indexed_from_db(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
) -> None:
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
    if not rows:
        return
    collection = _session_collection()
    existing_ids = {
        str((p.get("payload") or {}).get("summary_id") or "")
        for p in (_LOCAL_POINTS.get(collection) or [])
    }
    missing = [r for r in rows if r.summary_id not in existing_ids]
    if missing:
        index_conversation_summaries_sync(missing)


class VectorSessionRecall(MemoryRecallPort):
    def recall(
        self,
        *,
        user_id: int,
        conversation_id: int,
        query: str,
        limit: int = 8,
    ) -> EntityMatchResult:
        hits_v = vector_recall_session_sync(
            user_id=user_id,
            conversation_id=conversation_id,
            query=query,
            limit=limit,
        )
        hits = [
            EntityHit(
                kind="vector_summary",
                value=(h.core_need or h.summary_id)[:120],
                source="vector_memory",
                score=h.score,
                meta=h.to_item(),
            )
            for h in hits_v
        ]
        return EntityMatchResult(hits=hits, query_entities=[query] if query else [])


def clear_local_session_vectors() -> None:
    """自测用：清空进程内降级库。"""
    _LOCAL_POINTS.clear()


def index_tool_step_sync(
    *,
    user_id: int,
    conversation_id: int,
    task_id: str,
    tool: str,
    observation: str,
    run_id: str = "",
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> bool:
    """单次工具 Observation 分块写入短期会话向量库。"""
    text = (observation or "").strip()
    if len(text) < 8:
        return False
    tool_n = (tool or "tool").strip()[:64]
    excerpt = text[:1200]
    embed_src = f"工具:{tool_n}\n任务:{task_id}\n结果:{excerpt}"
    if embed_fn:
        vec = embed_fn([embed_src])[0]
    else:
        vec = lexical_embed(embed_src)
    pid = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"tool_step:{user_id}:{conversation_id}:{run_id}:{tool_n}:{excerpt[:80]}",
        )
    )
    point = {
        "id": pid,
        "vector": vec,
        "payload": {
            "kind": "tool_step",
            "summary_id": pid.replace("-", "")[:32],
            "user_id": int(user_id),
            "conversation_id": int(conversation_id),
            "task_id": task_id or "",
            "scene": "tool",
            "core_need": f"工具 {tool_n} 执行结果",
            "key_data": excerpt[:300],
            "raw_excerpt": excerpt,
            "text": embed_src[:2000],
            "tool": tool_n,
        },
    }
    return upsert_session_vectors([point], len(vec))


async def index_tool_step(
    *,
    user_id: int,
    conversation_id: int,
    task_id: str,
    tool: str,
    observation: str,
    run_id: str = "",
) -> bool:
    text = (observation or "").strip()
    if len(text) < 8:
        return False
    tool_n = (tool or "tool").strip()[:64]
    excerpt = text[:1200]
    embed_src = f"工具:{tool_n}\n任务:{task_id}\n结果:{excerpt}"
    vec = (await embed_texts([embed_src]))[0]
    pid = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"tool_step:{user_id}:{conversation_id}:{run_id}:{tool_n}:{excerpt[:80]}",
        )
    )
    point = {
        "id": pid,
        "vector": vec,
        "payload": {
            "kind": "tool_step",
            "summary_id": pid.replace("-", "")[:32],
            "user_id": int(user_id),
            "conversation_id": int(conversation_id),
            "task_id": task_id or "",
            "scene": "tool",
            "core_need": f"工具 {tool_n} 执行结果",
            "key_data": excerpt[:300],
            "raw_excerpt": excerpt,
            "text": embed_src[:2000],
            "tool": tool_n,
        },
    }
    return upsert_session_vectors([point], len(vec))


def index_user_memory_item_sync(
    *,
    user_id: int,
    item_id: int | str,
    content: str,
    kind: str = "preference",
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> bool:
    """长期用户记忆写入独立 collection（仅 user_id 隔离）。"""
    text = (content or "").strip()
    if len(text) < 4:
        return False
    embed_src = f"[{kind}] {text}"
    if embed_fn:
        vec = embed_fn([embed_src])[0]
    else:
        vec = lexical_embed(embed_src)
    collection = _user_memory_collection()
    pid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"user_memory:{user_id}:{item_id}"))
    point = {
        "id": pid,
        "vector": vec,
        "payload": {
            "kind": "long_term",
            "user_id": int(user_id),
            "item_id": str(item_id),
            "memory_kind": kind,
            "core_need": text[:240],
            "key_data": text[:300],
            "raw_excerpt": text[:1500],
            "text": embed_src[:2000],
            "scene": kind,
        },
    }
    try:
        from rag.qdrant_client import upsert_chunks

        if upsert_chunks([point], len(vec), collection=collection):
            return True
    except Exception as exc:
        logger.warning("user memory qdrant upsert failed: %s", exc)
    _upsert_local(collection, [point])
    return True


def search_user_memory_vectors(
    vector: list[float],
    *,
    user_id: int,
    top_k: int = 4,
    score_threshold: float | None = None,
) -> list[dict[str, Any]]:
    thr = score_threshold if score_threshold is not None else _score_threshold()
    collection = _user_memory_collection()
    try:
        from rag.qdrant_client import search_vectors_filtered

        hits = search_vectors_filtered(
            vector,
            collection=collection,
            must=[("user_id", user_id)],
            top_k=top_k,
            score_threshold=thr,
        )
        if hits:
            return hits
    except Exception as exc:
        logger.warning("user memory search failed: %s", exc)
    # 本地：不按 conversation 过滤
    store = _LOCAL_POINTS.get(collection) or []
    scored: list[tuple[float, dict[str, Any]]] = []
    for p in store:
        pl = p.get("payload") or {}
        if int(pl.get("user_id") or 0) != int(user_id):
            continue
        score = _cosine(vector, p.get("vector") or [])
        if score >= thr:
            item = dict(pl)
            item["score"] = round(score, 4)
            scored.append((score, item))
    scored.sort(key=lambda x: -x[0])
    return [x[1] for x in scored[:top_k]]


def recall_user_memory_sync(
    *,
    user_id: int,
    query: str,
    limit: int = 4,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    if embed_fn:
        vec = embed_fn([q])[0]
    else:
        vec = lexical_embed(q)
    return search_user_memory_vectors(vec, user_id=user_id, top_k=limit)
