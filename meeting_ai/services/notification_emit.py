"""在业务状态变更后向在线用户推送通知。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from api.permissions import can_approve_download_requests, can_approve_view_requests
from db.models import User
from services.notification_hub import notification_hub


def _user_id_by_username(db: Session, username: str) -> int | None:
    user = db.query(User).filter(User.username == username).first()
    return user.id if user else None


def _view_reviewer_ids(db: Session) -> list[int]:
    return [user.id for user in db.query(User).all() if can_approve_view_requests(user)]


def _download_reviewer_ids(db: Session) -> list[int]:
    return [user.id for user in db.query(User).all() if can_approve_download_requests(user)]


def notify_meeting_invite(db: Session, invitee_username: str) -> None:
    user_id = _user_id_by_username(db, invitee_username)
    if user_id:
        notification_hub.publish(user_id, {"channel": "meeting_invite", "action": "created"})


def notify_meeting_access_created(db: Session, applicant_id: int, kind: str) -> None:
    reviewer_ids = _view_reviewer_ids(db) if kind == "view" else _download_reviewer_ids(db)
    event = {"channel": "meeting_access", "action": "created", "kind": kind}
    notification_hub.publish_many(reviewer_ids, event)
    notification_hub.publish(applicant_id, {"channel": "meeting_access", "action": "submitted", "kind": kind})


def notify_meeting_realtime_complete(user_id: int, file_id: str) -> None:
    notification_hub.publish(
        user_id,
        {
            "channel": "meeting_realtime",
            "action": "completed",
            "file_id": file_id,
        },
    )


def notify_meeting_access_reviewed(applicant_id: int | None, kind: str, status: str) -> None:
    if not applicant_id:
        return
    notification_hub.publish(
        applicant_id,
        {
            "channel": "meeting_access",
            "action": "reviewed",
            "kind": kind,
            "status": status,
        },
    )
