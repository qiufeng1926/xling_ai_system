"""协作会议 REST API"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth_utils import get_current_user, get_db
from db.models import User
from services import collaborative_service as svc

router = APIRouter()


class CreateRoomRequest(BaseModel):
    meeting_name: str = Field(..., min_length=1, max_length=255)


class InviteItem(BaseModel):
    username: str
    role: Literal["recorder", "viewer"] = "recorder"


class InviteRequest(BaseModel):
    invitees: list[InviteItem] = Field(..., min_length=1)


@router.post("/meetings/rooms")
def create_room(body: CreateRoomRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        room = svc.create_room(db, user, body.meeting_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "room": room.to_dict(), "my_role": "host"}


@router.get("/meetings/rooms/mine")
def list_my_rooms(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"success": True, **svc.list_my_rooms(db, user.username)}


@router.get("/meetings/rooms/invitations")
def list_pending_invitations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = svc.list_my_rooms(db, user.username)
    return {"success": True, "items": data["pending_invitations"]}


@router.get("/meetings/rooms/{room_code}")
def get_room(room_code: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    room = svc.get_room_by_code(db, room_code)
    if not room:
        raise HTTPException(status_code=404, detail="会议不存在")
    if not svc.can_access_room(db, room, user.username):
        raise HTTPException(status_code=403, detail="无权查看该会议（仅参会人员可查看）")
    return {"success": True, **svc.build_room_state(db, room, user.username)}


@router.post("/meetings/rooms/{room_code}/invite")
def invite_to_room(
    room_code: str,
    body: InviteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    room = svc.get_room_by_code(db, room_code)
    if not room:
        raise HTTPException(status_code=404, detail="会议不存在")
    try:
        items = svc.invite_users(
            db,
            room,
            user.username,
            [i.model_dump() for i in body.invitees],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "invitations": [i.to_dict() for i in items]}


@router.post("/meetings/rooms/{room_code}/accept")
def accept_invitation(room_code: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    room = svc.get_room_by_code(db, room_code)
    if not room:
        raise HTTPException(status_code=404, detail="会议不存在")
    try:
        inv = svc.accept_invitation(db, room, user.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "invitation": inv.to_dict(), **svc.build_room_state(db, room, user.username)}


@router.post("/meetings/rooms/{room_code}/join")
def join_room(room_code: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    room = svc.get_room_by_code(db, room_code)
    if not room:
        raise HTTPException(status_code=404, detail="会议不存在")
    try:
        state = svc.join_room(db, room, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, **state}


@router.post("/meetings/rooms/{room_code}/start")
async def start_room(room_code: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from services.room_runtime import room_manager

    room = svc.get_room_by_code(db, room_code)
    if not room:
        raise HTTPException(status_code=404, detail="会议不存在")
    try:
        room = svc.start_room(db, room, user.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rt = room_manager.get_room(room.room_code)
    if rt:
        rt.status = "live"
    await room_manager.broadcast(room.room_code, {
        "type": "room_status",
        "status": "live",
        "room_code": room.room_code,
    })
    return {"success": True, "room": room.to_dict()}


@router.post("/meetings/rooms/{room_code}/end")
async def end_room(room_code: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from api.collaborative_ws import finalize_collaborative_room

    room = svc.get_room_by_code(db, room_code)
    if not room:
        raise HTTPException(status_code=404, detail="会议不存在")
    try:
        room = svc.end_room(db, room, user.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await finalize_collaborative_room(db, room)
    db.refresh(room)
    return {"success": True, "room": room.to_dict()}
