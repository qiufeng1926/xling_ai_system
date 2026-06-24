"""门户内部 API：员工离职交接"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth_utils import get_db
from config.config import portal_internal_key
from db.models import (
    CollaborativeRoom,
    Meeting,
    MeetingDownloadGrant,
    MeetingDownloadRequest,
    MeetingViewGrant,
    MeetingViewRequest,
    User,
)

router = APIRouter(prefix="/internal/offboard", tags=["内部-离职交接"])


def _verify_key(x_portal_internal_key: str = Header(default="")) -> None:
    expected = (portal_internal_key or "").strip()
    if not expected or x_portal_internal_key != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无效的内部密钥")


class OffboardRequest(BaseModel):
    departed_username: str = Field(..., min_length=1, max_length=64)
    handover_username: str = Field(..., min_length=1, max_length=64)
    offboarding_id: int = Field(..., ge=1)


class RevertRequest(BaseModel):
    snapshot: dict = Field(default_factory=dict)


def _get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username.strip()).first()


@router.post("", dependencies=[Depends(_verify_key)])
def offboard_user(body: OffboardRequest, db: Session = Depends(get_db)):
    departed = _get_user_by_username(db, body.departed_username)
    handover = _get_user_by_username(db, body.handover_username)
    if not departed:
        raise HTTPException(status_code=400, detail=f"会议模块未找到用户: {body.departed_username}")
    if not handover:
        raise HTTPException(status_code=400, detail=f"会议模块未找到用户: {body.handover_username}")

    snapshot: dict = {
        "offboarding_id": body.offboarding_id,
        "meetings": [],
        "rooms": [],
        "view_requests": [],
        "download_requests": [],
        "view_grants_deleted": [],
        "download_grants_deleted": [],
    }
    now = datetime.now()

    meetings = db.query(Meeting).filter(Meeting.user_id == departed.id).all()
    for meeting in meetings:
        snapshot["meetings"].append({"file_id": meeting.file_id, "old_user_id": departed.id, "new_user_id": handover.id})
        meeting.user_id = handover.id

    rooms = db.query(CollaborativeRoom).filter(
        CollaborativeRoom.host_user_id == departed.id,
    ).all()
    for room in rooms:
        snapshot["rooms"].append(
            {
                "room_id": room.id,
                "old_host_user_id": room.host_user_id,
                "old_host_username": room.host_username,
                "new_host_user_id": handover.id,
                "new_host_username": handover.username,
            }
        )
        room.host_user_id = handover.id
        room.host_username = handover.username

    for model, key in (
        (MeetingViewRequest, "view_requests"),
        (MeetingDownloadRequest, "download_requests"),
    ):
        for req in db.query(model).filter(model.user_id == departed.id).all():
            if req.status == "pending":
                snapshot[key].append({"id": req.id, "old_status": req.status})
                req.status = "rejected"
                req.review_note = "员工离职，申请自动拒绝"
                req.reviewed_at = now
            if req.applicant_username is None:
                req.applicant_username = departed.username
                req.applicant_nickname = departed.nickname

        for req in db.query(model).filter(model.reviewer_id == departed.id, model.status == "pending").all():
            snapshot[key].append(
                {
                    "id": req.id,
                    "old_reviewer_id": req.reviewer_id,
                    "reassigned": True,
                }
            )
            req.reviewer_id = handover.id
            req.reviewer_username = handover.username
            req.reviewer_nickname = handover.nickname

    for model, key in (
        (MeetingViewGrant, "view_grants_deleted"),
        (MeetingDownloadGrant, "download_grants_deleted"),
    ):
        grants = db.query(model).filter(model.user_id == departed.id).all()
        for grant in grants:
            snapshot[key].append({"id": grant.id, "user_id": grant.user_id, "file_id": grant.file_id})
            db.delete(grant)

    db.commit()
    return {"success": True, "snapshot": snapshot}


@router.post("/revert", dependencies=[Depends(_verify_key)])
def revert_offboard(body: RevertRequest, db: Session = Depends(get_db)):
    snap = body.snapshot or {}

    for item in snap.get("meetings") or []:
        meeting = db.query(Meeting).filter(Meeting.file_id == item.get("file_id")).first()
        if meeting:
            meeting.user_id = item.get("old_user_id")

    for item in snap.get("rooms") or []:
        room = db.query(CollaborativeRoom).filter(CollaborativeRoom.id == item.get("room_id")).first()
        if room:
            room.host_user_id = item.get("old_host_user_id")
            room.host_username = item.get("old_host_username")

    for item in snap.get("view_requests") or []:
        req = db.query(MeetingViewRequest).filter(MeetingViewRequest.id == item.get("id")).first()
        if req and not item.get("reassigned"):
            req.status = item.get("old_status") or "pending"
            req.review_note = None
            req.reviewed_at = None
        elif req and item.get("reassigned"):
            req.reviewer_id = item.get("old_reviewer_id")

    for item in snap.get("download_requests") or []:
        req = db.query(MeetingDownloadRequest).filter(MeetingDownloadRequest.id == item.get("id")).first()
        if req and not item.get("reassigned"):
            req.status = item.get("old_status") or "pending"
            req.review_note = None
            req.reviewed_at = None
        elif req and item.get("reassigned"):
            req.reviewer_id = item.get("old_reviewer_id")

    db.commit()
    return {"success": True}
