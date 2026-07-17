from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agent.orchestrator import resume_after_confirmation, resume_chat_after_confirmation
from api.auth_utils import get_current_user, require_user_id
from api.portal_auth import PortalUser
from db.models import Confirmation
from db.session import get_db

router = APIRouter(prefix="/v1/confirmations", tags=["confirmations"])


class ConfirmBody(BaseModel):
    approved: bool


@router.get("/{confirmation_id}")
def get_confirmation(
    confirmation_id: int,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    row = db.get(Confirmation, confirmation_id)
    if not row or row.user_id != uid:
        raise HTTPException(404, "确认单不存在")
    return {
        "id": row.id,
        "action_type": row.action_type,
        "status": row.status,
        "payload_json": row.payload_json,
        "conversation_id": row.conversation_id,
        "run_id": row.run_id,
    }


@router.post("/{confirmation_id}")
async def resolve_confirmation(
    confirmation_id: int,
    body: ConfirmBody,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """兼容旧客户端：拒绝直接落库；同意返回 need_resume_stream，请走 /resume。"""
    uid = require_user_id(user)
    result = await resume_after_confirmation(
        db, user_id=uid, confirmation_id=confirmation_id, approved=body.approved
    )
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "处理失败")
    return result


@router.post("/{confirmation_id}/resume")
async def resume_confirmation_stream(
    confirmation_id: int,
    body: ConfirmBody,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """SSE：同意后恢复检查点并继续 ReAct；拒绝则短答复结束。"""
    uid = require_user_id(user)
    row = db.get(Confirmation, confirmation_id)
    if not row or row.user_id != uid:
        raise HTTPException(404, "确认单不存在")

    async def gen():
        async for chunk in resume_chat_after_confirmation(
            db, user_id=uid, confirmation_id=confirmation_id, approved=body.approved
        ):
            yield chunk

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
