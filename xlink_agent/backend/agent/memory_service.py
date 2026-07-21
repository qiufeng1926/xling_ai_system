from __future__ import annotations

import json

from sqlalchemy.orm import Session

from db.models import MemoryItem, MemoryProfile


def get_or_create_profile(db: Session, user_id: int) -> MemoryProfile:
    row = db.get(MemoryProfile, user_id)
    if row is None:
        row = MemoryProfile(user_id=user_id, summary="", preferences_json="{}")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def build_memory_context(db: Session, user_id: int, limit: int = 8) -> str:
    profile = get_or_create_profile(db, user_id)
    items = (
        db.query(MemoryItem)
        .filter(MemoryItem.user_id == user_id)
        .order_by(MemoryItem.id.desc())
        .limit(limit)
        .all()
    )
    parts = []
    if profile.summary:
        parts.append(f"用户画像摘要：{profile.summary}")
    prefs = profile.preferences_json or "{}"
    try:
        prefs_obj = json.loads(prefs)
        if prefs_obj:
            parts.append(f"用户偏好：{json.dumps(prefs_obj, ensure_ascii=False)}")
    except Exception:
        pass
    for it in reversed(items):
        parts.append(f"- [{it.kind}] {it.content}")
    return "\n".join(parts) if parts else ""


def maybe_update_profile_from_dialog(db: Session, user_id: int, user_text: str) -> None:
    """轻量写入：把用户明确偏好记入 memory_items，并同步长期向量。"""
    keywords = ("我喜欢", "请记住", "以后都", "我的偏好", "我叫")
    if not any(k in user_text for k in keywords):
        return
    row = MemoryItem(
        user_id=user_id,
        kind="preference",
        content=user_text[:1000],
        source_ref="dialog",
        score=1,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    try:
        from agent.vector_memory import index_user_memory_item_sync

        index_user_memory_item_sync(
            user_id=user_id,
            item_id=row.id or user_text[:32],
            content=row.content,
            kind=row.kind or "preference",
        )
    except Exception:
        pass
