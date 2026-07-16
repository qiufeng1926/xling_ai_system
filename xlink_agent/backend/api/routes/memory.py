from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agent.memory_service import get_or_create_profile
from api.auth_utils import get_current_user, require_user_id
from api.portal_auth import PortalUser
from db.models import MemoryItem
from db.session import get_db

router = APIRouter(prefix="/v1/memory", tags=["memory"])


class ProfilePatch(BaseModel):
    summary: str | None = None
    preferences: dict | None = None


@router.get("/profile")
def get_profile(
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    profile = get_or_create_profile(db, uid)
    items = (
        db.query(MemoryItem)
        .filter(MemoryItem.user_id == uid)
        .order_by(MemoryItem.id.desc())
        .limit(50)
        .all()
    )
    prefs = {}
    try:
        prefs = json.loads(profile.preferences_json or "{}")
    except Exception:
        pass
    return {
        "summary": profile.summary,
        "preferences": prefs,
        "items": [
            {"id": i.id, "kind": i.kind, "content": i.content, "created_at": i.created_at.isoformat() if i.created_at else None}
            for i in items
        ],
    }


@router.patch("/profile")
def patch_profile(
    body: ProfilePatch,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    profile = get_or_create_profile(db, uid)
    if body.summary is not None:
        profile.summary = body.summary[:5000]
    if body.preferences is not None:
        profile.preferences_json = json.dumps(body.preferences, ensure_ascii=False)
    db.commit()
    return {"ok": True}
