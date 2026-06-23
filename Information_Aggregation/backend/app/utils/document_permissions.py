"""云文档镜像访问权限（规则对齐 meeting_ai 会议记录）"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.constants.roles import ADMIN, SUPER_ADMIN
from app.models import User
from app.models.feishu_document import (
    FeishuDocumentDownloadGrant,
    FeishuDocumentMirror,
    FeishuDocumentViewGrant,
)
from app.utils.access_control import (
    is_hidden_super_user,
    is_super_admin,
    normalize_role,
    should_hide_user_from,
)
from app.utils.user_permissions import effective_permissions

ROOT_DOCUMENT_VIEW_DAYS = 3


def _has_view_grant(db: Session, viewer: User, doc_id: str) -> bool:
    identity = [FeishuDocumentViewGrant.user_id == viewer.id]
    if viewer.username:
        identity.append(FeishuDocumentViewGrant.username == viewer.username)
    return (
        db.query(FeishuDocumentViewGrant)
        .filter(FeishuDocumentViewGrant.doc_id == doc_id, or_(*identity))
        .first()
        is not None
    )


def _has_download_grant(db: Session, viewer: User, doc_id: str) -> bool:
    identity = [FeishuDocumentDownloadGrant.user_id == viewer.id]
    if viewer.username:
        identity.append(FeishuDocumentDownloadGrant.username == viewer.username)
    return (
        db.query(FeishuDocumentDownloadGrant)
        .filter(FeishuDocumentDownloadGrant.doc_id == doc_id, or_(*identity))
        .first()
        is not None
    )


def _is_other_super_admin_doc(viewer: User, mirror: FeishuDocumentMirror, owner: User | None) -> bool:
    if owner is not None and is_hidden_super_user(owner) and not is_hidden_super_user(viewer):
        return True
    return (
        owner is not None
        and is_super_admin(owner)
        and owner.id != viewer.id
        and mirror.user_id == owner.id
    )


def can_view_all_documents(user: User) -> bool:
    if is_super_admin(user):
        return True
    return bool(effective_permissions(user).get("view_all_meetings"))


def can_view_peer_super_admin_documents(user: User) -> bool:
    return is_super_admin(user) and bool(effective_permissions(user).get("view_all_root_meetings"))


def can_download_documents_globally(user: User) -> bool:
    if is_super_admin(user):
        return True
    return bool(effective_permissions(user).get("download_meetings"))


def can_approve_document_view(user: User) -> bool:
    if is_super_admin(user):
        return True
    return bool(effective_permissions(user).get("approve_meeting_view"))


def can_approve_document_download(user: User) -> bool:
    if is_super_admin(user):
        return True
    return bool(effective_permissions(user).get("approve_meeting_download"))


def can_access_document(
    db: Session,
    viewer: User,
    mirror: FeishuDocumentMirror,
    owner: User | None = None,
) -> bool:
    if mirror.user_id == viewer.id:
        return True

    owner = owner or db.query(User).filter(User.id == mirror.user_id).first()

    if is_super_admin(viewer):
        if _is_other_super_admin_doc(viewer, mirror, owner):
            return can_view_peer_super_admin_documents(viewer)
        return True

    if _has_view_grant(db, viewer, mirror.doc_id):
        return True

    if can_view_all_documents(viewer):
        return True

    if owner is not None and should_hide_user_from(viewer, owner):
        return False

    owner_role = normalize_role(owner.role) if owner else None
    if owner_role == SUPER_ADMIN:
        perms = effective_permissions(viewer)
        if normalize_role(viewer.role) != ADMIN or not perms.get("view_root_meetings"):
            return False
        cutoff = datetime.now() - timedelta(days=ROOT_DOCUMENT_VIEW_DAYS)
        created = mirror.created_at
        return created is not None and created >= cutoff

    return False


def can_download_document(
    db: Session,
    viewer: User,
    mirror: FeishuDocumentMirror,
    owner: User | None = None,
) -> bool:
    if not can_access_document(db, viewer, mirror, owner):
        return False
    if is_super_admin(viewer) or can_download_documents_globally(viewer):
        return True
    if mirror.user_id == viewer.id:
        return True
    return _has_download_grant(db, viewer, mirror.doc_id)
