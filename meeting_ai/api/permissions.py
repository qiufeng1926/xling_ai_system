"""会议访问权限判断"""
from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from db.models import Meeting, User
from utils.hidden_user import is_hidden_super_user

ROOT_MEETING_VIEW_DAYS = 3


def _has_meeting_view_grant(session: Session, viewer: User, file_id: str) -> bool:
    from db.models import MeetingViewGrant

    filters = [MeetingViewGrant.file_id == file_id]
    identity = [MeetingViewGrant.user_id == viewer.id]
    if viewer.username:
        identity.append(MeetingViewGrant.username == viewer.username)
    return (
        session.query(MeetingViewGrant)
        .filter(*filters, or_(*identity))
        .first()
        is not None
    )


def _is_other_root_meeting(viewer: User, meeting: Meeting, owner: User | None) -> bool:
    if owner is not None and is_hidden_super_user(owner) and not is_hidden_super_user(viewer):
        return True
    return (
        owner is not None
        and owner.is_root()
        and owner.id != viewer.id
        and meeting.user_id == owner.id
    )


def can_access_meeting(
    viewer: User,
    meeting: Meeting,
    owner: User | None,
    *,
    session: Session | None = None,
) -> bool:
    """判断用户是否有权查看某条会议记录"""
    if session is None:
        from db.session import SessionFactory

        db = SessionFactory()
        try:
            return can_access_meeting(viewer, meeting, owner, session=db)
        finally:
            db.close()

    if meeting.user_id == viewer.id:
        return True

    if viewer.is_root():
        if _is_other_root_meeting(viewer, meeting, owner):
            return viewer.can_view_peer_root_meetings()
        return True

    # 单条会议浏览授权（审批通过），优先于协作/超管会议等默认限制
    if _has_meeting_view_grant(session, viewer, meeting.file_id):
        return True

    if viewer.can_view_all_meetings():
        return True

    if getattr(meeting, "is_collaborative", False):
        from services.collaborative_service import is_meeting_participant

        return is_meeting_participant(session, meeting, viewer.username)

    owner_role = owner.role if owner else None

    if owner is not None and is_hidden_super_user(owner) and not is_hidden_super_user(viewer):
        return False

    if owner_role == "root":
        if viewer.role != "admin" or not viewer.can_view_root_meetings:
            return False
        cutoff = datetime.now() - timedelta(days=ROOT_MEETING_VIEW_DAYS)
        return meeting.created_at is not None and meeting.created_at >= cutoff

    return False


def can_download_files(user: User) -> bool:
    """是否可全局下载/导出（超级管理员或已授权）"""
    if user.is_root():
        return True
    return bool(getattr(user, 'can_download', False))


def _has_meeting_download_grant(session: Session, viewer: User, file_id: str) -> bool:
    from db.models import MeetingDownloadGrant

    identity = [MeetingDownloadGrant.user_id == viewer.id]
    if viewer.username:
        identity.append(MeetingDownloadGrant.username == viewer.username)
    return (
        session.query(MeetingDownloadGrant)
        .filter(MeetingDownloadGrant.file_id == file_id, or_(*identity))
        .first()
        is not None
    )


def can_download_meeting(
    viewer: User,
    meeting: Meeting,
    owner: User | None,
    *,
    session: Session | None = None,
) -> bool:
    """是否可下载/导出指定会议"""
    if session is None:
        from db.session import SessionFactory

        db = SessionFactory()
        try:
            return can_download_meeting(viewer, meeting, owner, session=db)
        finally:
            db.close()

    if viewer.is_root() or viewer.can_download_files():
        return True
    if meeting.user_id == viewer.id:
        return True
    if not can_access_meeting(viewer, meeting, owner, session=session):
        return False
    return _has_meeting_download_grant(session, viewer, meeting.file_id)


def can_approve_download_requests(user: User) -> bool:
    """是否可审批「下载权限」申请（超级管理员默认可；管理员需被授权）"""
    if user.is_root():
        return True
    return user.role == 'admin' and bool(getattr(user, 'can_approve_download', False))
