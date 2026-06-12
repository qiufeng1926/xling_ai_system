"""会议访问权限判断"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from db.models import Meeting, User
from utils.hidden_user import is_hidden_super_user

ROOT_MEETING_VIEW_DAYS = 3


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
    if getattr(meeting, "is_collaborative", False):
        from services.collaborative_service import is_meeting_participant

        if session is not None:
            return is_meeting_participant(session, meeting, viewer.username)

        from db.session import SessionFactory

        db = SessionFactory()
        try:
            return is_meeting_participant(db, meeting, viewer.username)
        finally:
            db.close()

    if meeting.user_id == viewer.id:
        return True

    if viewer.is_root():
        if _is_other_root_meeting(viewer, meeting, owner):
            return viewer.can_view_peer_root_meetings()
        return True

    owner_role = owner.role if owner else None

    if owner is not None and is_hidden_super_user(owner) and not is_hidden_super_user(viewer):
        return False

    if owner_role == "root":
        if viewer.role != "admin" or not viewer.can_view_root_meetings:
            return False
        cutoff = datetime.now() - timedelta(days=ROOT_MEETING_VIEW_DAYS)
        return meeting.created_at is not None and meeting.created_at >= cutoff

    if viewer.role == "admin" or viewer.can_view_all:
        return True

    return False


def can_download_files(user: User) -> bool:
    """是否可导出/下载 Word、图文等文件（超级管理员默认允许）"""
    if user.is_root():
        return True
    return bool(getattr(user, 'can_download', False))


def can_approve_download_requests(user: User) -> bool:
    """是否可审批「下载权限」申请（超级管理员默认可；管理员需被授权）"""
    if user.is_root():
        return True
    return user.role == 'admin' and bool(getattr(user, 'can_approve_download', False))
