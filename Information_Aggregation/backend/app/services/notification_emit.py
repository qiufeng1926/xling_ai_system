"""在业务状态变更后向在线用户推送通知。"""

from __future__ import annotations

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.constants.permissions import (
    REQ_DOWNLOAD_MEETINGS,
    REQ_PROMOTE_ADMIN,
    REQ_VIEW_ALL_MEETINGS,
    REQ_VIEW_LIBRARY,
    REQ_VIEW_ROOT_MEETINGS,
)
from app.constants.roles import ADMIN, SUPER_ADMIN
from app.models import User
from app.services.notification_hub import notification_hub
from app.utils.document_permissions import can_approve_document_download, can_approve_document_view


def _reviewer_ids_for_access_request(db: Session, request_type: str) -> list[int]:
    query = db.query(User.id).filter(User.status == 1)
    if request_type == REQ_VIEW_LIBRARY:
        query = query.filter(User.role.in_([SUPER_ADMIN, ADMIN]))
    elif request_type in (REQ_VIEW_ALL_MEETINGS, REQ_VIEW_ROOT_MEETINGS, REQ_PROMOTE_ADMIN):
        query = query.filter(User.role == SUPER_ADMIN)
    elif request_type == REQ_DOWNLOAD_MEETINGS:
        query = query.filter(
            or_(
                User.role == SUPER_ADMIN,
                and_(User.role == ADMIN, User.approve_meeting_download == 1),
            )
        )
    else:
        return []
    return [row[0] for row in query.all()]


def _feishu_doc_reviewer_ids(db: Session, kind: str) -> list[int]:
    ids: list[int] = []
    for user in db.query(User).filter(User.status == 1).all():
        if kind == "view" and can_approve_document_view(user):
            ids.append(user.id)
        elif kind == "download" and can_approve_document_download(user):
            ids.append(user.id)
    return ids


def notify_access_request_created(db: Session, user_id: int | None, request_type: str) -> None:
    event = {"channel": "access_request", "action": "created", "request_type": request_type}
    reviewer_ids = _reviewer_ids_for_access_request(db, request_type)
    notification_hub.publish_many(reviewer_ids, event)
    if user_id:
        notification_hub.publish(user_id, {"channel": "access_request", "action": "submitted"})


def notify_access_request_reviewed(user_id: int | None, request_type: str, status: str) -> None:
    if not user_id:
        return
    notification_hub.publish(
        user_id,
        {
            "channel": "access_request",
            "action": "reviewed",
            "request_type": request_type,
            "status": status,
        },
    )


def notify_feishu_doc_request_created(
    db: Session, user_id: int, kind: str, count: int = 1
) -> None:
    if count <= 0:
        return
    event = {"channel": "feishu_doc_access", "action": "created", "kind": kind}
    notification_hub.publish_many(_feishu_doc_reviewer_ids(db, kind), event)
    notification_hub.publish(user_id, {"channel": "feishu_doc_access", "action": "submitted", "kind": kind})


def notify_feishu_doc_request_reviewed(user_id: int, kind: str, status: str) -> None:
    notification_hub.publish(
        user_id,
        {
            "channel": "feishu_doc_access",
            "action": "reviewed",
            "kind": kind,
            "status": status,
        },
    )


def _super_admin_ids(db: Session) -> list[int]:
    return [
        row[0]
        for row in db.query(User.id).filter(User.role == SUPER_ADMIN, User.status == 1).all()
    ]


def notify_offboarding_pending(db: Session, record) -> None:
    user = db.query(User).filter(User.id == record.user_id).first()
    event = {
        "channel": "user_offboarding",
        "action": "pending",
        "offboarding_id": record.id,
        "departed_username": user.username if user else None,
        "departed_nickname": (user.nickname or user.username) if user else None,
    }
    notification_hub.publish_many(_super_admin_ids(db), event)


def notify_offboarding_completed(db: Session, record) -> None:
    user = db.query(User).filter(User.id == record.user_id).first()
    handover = (
        db.query(User).filter(User.id == record.handover_user_id).first()
        if record.handover_user_id
        else None
    )
    summary = record.content_snapshot or {}
    event = {
        "channel": "user_offboarding",
        "action": "completed",
        "offboarding_id": record.id,
        "departed_username": user.username if user else None,
        "departed_nickname": (user.nickname or user.username) if user else None,
        "handover_username": handover.username if handover else None,
        "summary": summary,
    }
    targets = set(_super_admin_ids(db))
    if record.handover_user_id:
        targets.add(record.handover_user_id)
    notification_hub.publish_many(list(targets), event)
