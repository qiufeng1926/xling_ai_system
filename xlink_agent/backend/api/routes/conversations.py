from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agent.orchestrator import run_chat
from api.auth_utils import get_current_user, require_user_id
from api.portal_auth import PortalUser
from db.models import Conversation, Message
from db.session import get_db

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


class ConversationCreate(BaseModel):
    title: str = "新对话"


class ConversationPatch(BaseModel):
    title: str | None = None
    status: str | None = None


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=20000)


def _conv_dict(c: Conversation) -> dict[str, Any]:
    return {
        "id": c.id,
        "title": c.title,
        "status": c.status,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@router.get("")
def list_conversations(
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    rows = (
        db.query(Conversation)
        .filter(Conversation.user_id == uid, Conversation.status != "deleted")
        .order_by(Conversation.updated_at.desc())
        .limit(100)
        .all()
    )
    return {"items": [_conv_dict(r) for r in rows]}


@router.post("")
def create_conversation(
    body: ConversationCreate,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    row = Conversation(user_id=uid, title=body.title or "新对话")
    db.add(row)
    db.commit()
    db.refresh(row)
    return _conv_dict(row)


@router.get("/{conversation_id}")
def get_conversation(
    conversation_id: int,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    row = db.get(Conversation, conversation_id)
    if not row or row.user_id != uid:
        raise HTTPException(404, "会话不存在")
    return _conv_dict(row)


@router.patch("/{conversation_id}")
def patch_conversation(
    conversation_id: int,
    body: ConversationPatch,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    row = db.get(Conversation, conversation_id)
    if not row or row.user_id != uid:
        raise HTTPException(404, "会话不存在")
    if body.title is not None:
        row.title = body.title[:200]
    if body.status is not None:
        row.status = body.status
    db.commit()
    return _conv_dict(row)


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    row = db.get(Conversation, conversation_id)
    if not row or row.user_id != uid:
        raise HTTPException(404, "会话不存在")
    row.status = "deleted"
    db.commit()
    return {"ok": True}


@router.get("/{conversation_id}/messages")
def list_messages(
    conversation_id: int,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    row = db.get(Conversation, conversation_id)
    if not row or row.user_id != uid:
        raise HTTPException(404, "会话不存在")
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.id.asc())
        .all()
    )
    return {
        "items": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "files": _message_files(m.metadata_json),
            }
            for m in msgs
        ]
    }


def _message_files(metadata_json: str | None) -> list[dict]:
    if not metadata_json:
        return []
    try:
        meta = json.loads(metadata_json)
    except Exception:
        return []
    files = meta.get("files") if isinstance(meta, dict) else None
    if not isinstance(files, list):
        return []
    out = []
    for f in files:
        if isinstance(f, dict) and f.get("file_id"):
            out.append({"file_id": f["file_id"], "name": f.get("name")})
    return out


@router.post("/{conversation_id}/chat")
async def chat(
    conversation_id: int,
    body: ChatBody,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    row = db.get(Conversation, conversation_id)
    if not row or row.user_id != uid:
        raise HTTPException(404, "会话不存在")
    if row.title == "新对话":
        row.title = body.message.strip()[:40] or "新对话"
        db.commit()

    async def event_gen():
        async for chunk in run_chat(
            db, user_id=uid, conversation_id=conversation_id, user_text=body.message.strip()
        ):
            yield chunk

    return StreamingResponse(event_gen(), media_type="text/event-stream")
