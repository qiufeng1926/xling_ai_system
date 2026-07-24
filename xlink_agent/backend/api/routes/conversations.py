from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agent.orchestrator import run_chat
from api.auth_utils import get_current_user, require_user_id
from api.portal_auth import PortalUser
from db.models import Conversation, Message
from db.session import get_db
from skills.scoped import CONVERSATION_SCOPED_SKILLS
from tools.portal_context import reset_portal_bearer, set_portal_bearer

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


class ConversationCreate(BaseModel):
    title: str = "新对话"
    skill_slug: str | None = Field(default=None, max_length=120)


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
        "skill_slug": getattr(c, "skill_slug", None),
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _bearer_from_request(request: Request) -> str:
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


@router.get("")
def list_conversations(
    skill_slug: str | None = Query(default=None),
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    q = db.query(Conversation).filter(
        Conversation.user_id == uid, Conversation.status != "deleted"
    )
    if skill_slug:
        q = q.filter(Conversation.skill_slug == skill_slug)
    else:
        # 默认列表排除会话级筛库对话，避免污染通用 AgentHub
        q = q.filter(
            (Conversation.skill_slug.is_(None))
            | (~Conversation.skill_slug.in_(list(CONVERSATION_SCOPED_SKILLS)))
        )
    rows = q.order_by(Conversation.updated_at.desc()).limit(100).all()
    return {"items": [_conv_dict(r) for r in rows]}


@router.post("")
def create_conversation(
    body: ConversationCreate,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    slug = (body.skill_slug or "").strip() or None
    if slug in CONVERSATION_SCOPED_SKILLS:
        raise HTTPException(
            400,
            "商单筛库会话请走 /api/agent/v1/match/conversations，勿使用通用对话接口",
        )
    row = Conversation(
        user_id=uid,
        title=body.title or "新对话",
        skill_slug=slug,
    )
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
                "citations": _message_citations(m.metadata_json),
                "trajectory": _message_trajectory(m.metadata_json),
                "react_steps": _message_react_steps(m.metadata_json),
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


def _message_citations(metadata_json: str | None) -> list[dict]:
    if not metadata_json:
        return []
    try:
        meta = json.loads(metadata_json)
    except Exception:
        return []
    items = meta.get("citations") if isinstance(meta, dict) else None
    if not isinstance(items, list):
        return []
    out = []
    for c in items:
        if isinstance(c, dict) and (c.get("title") or c.get("url")):
            out.append(
                {
                    "title": c.get("title") or "",
                    "url": c.get("url") or "",
                    "snippet": c.get("snippet") or "",
                }
            )
    return out


def _message_trajectory(metadata_json: str | None) -> list[dict]:
    if not metadata_json:
        return []
    try:
        meta = json.loads(metadata_json)
    except Exception:
        return []
    items = meta.get("trajectory") if isinstance(meta, dict) else None
    return items if isinstance(items, list) else []


def _message_react_steps(metadata_json: str | None) -> list[dict]:
    if not metadata_json:
        return []
    try:
        meta = json.loads(metadata_json)
    except Exception:
        return []
    items = meta.get("react_steps") if isinstance(meta, dict) else None
    return items if isinstance(items, list) else []


@router.post("/{conversation_id}/chat")
async def chat(
    conversation_id: int,
    body: ChatBody,
    request: Request,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    row = db.get(Conversation, conversation_id)
    if not row or row.user_id != uid:
        raise HTTPException(404, "会话不存在")
    if row.title == "新对话" or (row.skill_slug and row.title in {"商单筛库", "新商单筛库"}):
        row.title = body.message.strip()[:40] or row.title
        db.commit()

    bearer = _bearer_from_request(request)

    async def event_gen():
        token = set_portal_bearer(bearer)
        try:
            async for chunk in run_chat(
                db, user_id=uid, conversation_id=conversation_id, user_text=body.message.strip()
            ):
                if await request.is_disconnected():
                    break
                yield chunk
        finally:
            reset_portal_bearer(token)

    return StreamingResponse(event_gen(), media_type="text/event-stream")
