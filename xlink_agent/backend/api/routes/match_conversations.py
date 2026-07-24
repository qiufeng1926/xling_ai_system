"""商单筛库专用 API：与通用 /v1/conversations 完全分离。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth_utils import get_current_user, require_user_id
from api.portal_auth import PortalUser
from db.models import Conversation, Message
from db.session import get_db
from match_agent import MATCH_SKILL_SLUG
from match_agent.orchestrator import run_match_chat
from tools.portal_context import reset_portal_bearer, set_portal_bearer

router = APIRouter(prefix="/v1/match", tags=["商单筛库"])


class MatchConversationCreate(BaseModel):
    title: str = "新商单筛库"


class MatchChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=20000)


def _bearer_from_request(request: Request) -> str:
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _conv_dict(c: Conversation) -> dict[str, Any]:
    return {
        "id": c.id,
        "title": c.title,
        "status": c.status,
        "skill_slug": c.skill_slug,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _ensure_match_conv(db: Session, uid: int, conversation_id: int) -> Conversation:
    row = db.get(Conversation, conversation_id)
    if not row or row.user_id != uid or row.status == "deleted":
        raise HTTPException(404, "会话不存在")
    if (row.skill_slug or "") != MATCH_SKILL_SLUG:
        raise HTTPException(400, "不是商单筛库会话")
    return row


@router.get("/conversations")
def list_match_conversations(
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    rows = (
        db.query(Conversation)
        .filter(
            Conversation.user_id == uid,
            Conversation.status != "deleted",
            Conversation.skill_slug == MATCH_SKILL_SLUG,
        )
        .order_by(Conversation.updated_at.desc())
        .limit(100)
        .all()
    )
    return {"items": [_conv_dict(r) for r in rows]}


@router.post("/conversations")
def create_match_conversation(
    body: MatchConversationCreate,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    row = Conversation(
        user_id=uid,
        title=(body.title or "新商单筛库")[:200],
        skill_slug=MATCH_SKILL_SLUG,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _conv_dict(row)


@router.delete("/conversations/{conversation_id}")
def delete_match_conversation(
    conversation_id: int,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    row = _ensure_match_conv(db, uid, conversation_id)
    row.status = "deleted"
    db.commit()
    return {"ok": True}


@router.get("/conversations/{conversation_id}/messages")
def list_match_messages(
    conversation_id: int,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    _ensure_match_conv(db, uid, conversation_id)
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.id.asc())
        .all()
    )
    items = []
    for m in msgs:
        traj = []
        influencers = []
        if m.metadata_json:
            try:
                meta = json.loads(m.metadata_json)
                if isinstance(meta, dict):
                    if isinstance(meta.get("trajectory"), list):
                        traj = meta["trajectory"]
                    if isinstance(meta.get("influencers"), list):
                        influencers = meta["influencers"]
            except Exception:
                pass
        items.append(
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "trajectory": traj,
                "influencers": influencers,
            }
        )
    return {"items": items}


@router.post("/conversations/{conversation_id}/chat")
async def match_chat(
    conversation_id: int,
    body: MatchChatBody,
    request: Request,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    row = _ensure_match_conv(db, uid, conversation_id)
    if row.title in {"新对话", "新商单筛库"}:
        row.title = body.message.strip()[:40] or row.title
        db.commit()

    bearer = _bearer_from_request(request)

    async def event_gen():
        token = set_portal_bearer(bearer)
        try:
            async for chunk in run_match_chat(
                db,
                user_id=uid,
                conversation_id=conversation_id,
                user_text=body.message.strip(),
            ):
                if await request.is_disconnected():
                    break
                yield chunk
        finally:
            reset_portal_bearer(token)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
