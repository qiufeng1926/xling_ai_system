from __future__ import annotations

from typing import Any

from utils.logger import get_logger

logger = get_logger("qdrant")

_client = None
_ready = False


def get_qdrant():
    """
    连接策略：
    - QDRANT_MODE=local（默认）：嵌入式落盘，开发机无需 Docker / 独立进程
    - QDRANT_MODE=url：连接 QDRANT_URL（生产 Compose 中的 qdrant 服务）
    """
    global _client, _ready
    if _client is not None:
        return _client
    try:
        from qdrant_client import QdrantClient

        from config.config import qdrant_mode, qdrant_path, qdrant_url

        mode = (qdrant_mode or "local").lower()
        if mode == "url":
            url = (qdrant_url or "").strip() or "http://127.0.0.1:6333"
            _client = QdrantClient(url=url, timeout=5.0)
            _client.get_collections()
            logger.info("Qdrant 已连接（url 模式）: %s", url)
        else:
            qdrant_path.mkdir(parents=True, exist_ok=True)
            _client = QdrantClient(path=str(qdrant_path))
            logger.info("Qdrant 已启用（local 嵌入式）: %s", qdrant_path)

        _ready = True
        return _client
    except Exception as exc:
        logger.warning("Qdrant 不可用，将降级为 MySQL 文本检索: %s", exc)
        _client = None
        _ready = False
        return None


def _default_collection() -> str:
    from config.config import qdrant_collection

    return qdrant_collection


def ensure_collection(vector_size: int, collection: str | None = None) -> bool:
    client = get_qdrant()
    if client is None:
        return False
    from qdrant_client.http import models as qm

    name = collection or _default_collection()
    names = [c.name for c in client.get_collections().collections]
    if name not in names:
        client.create_collection(
            collection_name=name,
            vectors_config=qm.VectorParams(size=vector_size, distance=qm.Distance.COSINE),
        )
    return True


def upsert_chunks(
    points: list[dict[str, Any]],
    vector_size: int,
    collection: str | None = None,
) -> bool:
    client = get_qdrant()
    if client is None:
        return False
    name = collection or _default_collection()
    if not ensure_collection(vector_size, collection=name):
        return False
    from qdrant_client.http import models as qm

    client.upsert(
        collection_name=name,
        points=[
            qm.PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
            for p in points
        ],
    )
    return True


def search_vectors(vector: list[float], *, user_id: int, top_k: int = 5) -> list[dict]:
    """知识库检索：global 或本人 private。"""
    client = get_qdrant()
    if client is None:
        return []
    from qdrant_client.http import models as qm

    name = _default_collection()
    try:
        flt = qm.Filter(
            should=[
                qm.FieldCondition(key="kind", match=qm.MatchValue(value="global")),
                qm.FieldCondition(key="user_id", match=qm.MatchValue(value=user_id)),
            ]
        )
        hits = client.search(
            collection_name=name,
            query_vector=vector,
            query_filter=flt,
            limit=top_k,
        )
        return [
            {
                "score": h.score,
                "text": (h.payload or {}).get("text"),
                "doc_id": (h.payload or {}).get("doc_id"),
                "kb_id": (h.payload or {}).get("kb_id"),
                "filename": (h.payload or {}).get("filename"),
            }
            for h in hits
        ]
    except Exception as exc:
        logger.warning("向量检索失败: %s", exc)
        return []


def search_vectors_filtered(
    vector: list[float],
    *,
    collection: str,
    must: list[tuple[str, Any]],
    top_k: int = 5,
    score_threshold: float | None = None,
) -> list[dict[str, Any]]:
    """通用过滤检索：must 为 (field, value) 精确匹配。"""
    client = get_qdrant()
    if client is None:
        return []
    from qdrant_client.http import models as qm

    try:
        conditions = [
            qm.FieldCondition(key=k, match=qm.MatchValue(value=v)) for k, v in must
        ]
        flt = qm.Filter(must=conditions) if conditions else None
        kwargs: dict[str, Any] = {
            "collection_name": collection,
            "query_vector": vector,
            "query_filter": flt,
            "limit": top_k,
        }
        if score_threshold is not None:
            kwargs["score_threshold"] = float(score_threshold)
        hits = client.search(**kwargs)
        out: list[dict[str, Any]] = []
        for h in hits:
            pl = dict(h.payload or {})
            pl["score"] = float(h.score or 0)
            out.append(pl)
        return out
    except Exception as exc:
        logger.warning("过滤向量检索失败 collection=%s: %s", collection, exc)
        return []
