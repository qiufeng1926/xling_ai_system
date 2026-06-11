"""会议访问权限判断"""
from datetime import datetime, timedelta

from db.models import Meeting, User

ROOT_MEETING_VIEW_DAYS = 3


def _is_other_root_meeting(viewer: User, meeting: Meeting, owner: User | None) -> bool:
    return (
        owner is not None
        and owner.is_root()
        and owner.id != viewer.id
        and meeting.user_id == owner.id
    )


def can_access_meeting(viewer: User, meeting: Meeting, owner: User | None) -> bool:
    """判断用户是否有权查看某条会议记录"""
    if meeting.user_id == viewer.id:
        return True

    if viewer.is_root():
        if _is_other_root_meeting(viewer, meeting, owner):
            return viewer.can_view_peer_root_meetings()
        return True

    owner_role = owner.role if owner else None

    if owner_role == 'root':
        if viewer.role != 'admin' or not viewer.can_view_root_meetings:
            return False
        cutoff = datetime.now() - timedelta(days=ROOT_MEETING_VIEW_DAYS)
        return meeting.created_at is not None and meeting.created_at >= cutoff

    if viewer.role == 'admin' or viewer.can_view_all:
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
