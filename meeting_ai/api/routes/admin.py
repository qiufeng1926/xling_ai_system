"""
超级管理员：账号管理与会议删除
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.auth_utils import get_current_user, get_db
from db.models import PermissionRequest, User, Meeting, MeetingDownloadLog
from db.session import delete_meeting_with_files
from utils.password import hash_password
from utils.logger import get_logger
from utils.hidden_user import hidden_super_user_ids, is_hidden_super_user

router = APIRouter()
logger = get_logger("admin_route")


def require_root(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_root():
        raise HTTPException(status_code=403, detail='仅超级管理员可执行此操作')
    return current_user


def _filter_users_for_admin_list(viewer: User, users: list[User]) -> list[User]:
    """无全量查阅权限的超级管理员在用户管理中看不到其他超级管理员（含秋枫AI）"""
    visible = users if is_hidden_super_user(viewer) else [u for u in users if not is_hidden_super_user(u)]
    if viewer.can_view_peer_root_meetings():
        return visible
    return [
        u for u in visible
        if not (u.is_root() and u.id != viewer.id)
    ]


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=64)


class UpdateUserRequest(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=32)
    role: str | None = Field(default=None, pattern='^(user|admin)$')
    can_view_all: bool | None = None
    can_view_root_meetings: bool | None = None
    can_download: bool | None = None
    can_approve_download: bool | None = None
    can_approve_view: bool | None = None


@router.get('/admin/users')
def list_users(
    current_user: User = Depends(require_root),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.created_at.asc()).all()
    visible = _filter_users_for_admin_list(current_user, users)
    return {'success': True, 'users': [u.to_dict() for u in visible]}


@router.patch('/admin/users/{user_id}')
def update_user(
    user_id: int,
    body: UpdateUserRequest,
    current_user: User = Depends(require_root),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail='用户不存在')
    if is_hidden_super_user(user) and not is_hidden_super_user(current_user):
        raise HTTPException(status_code=404, detail='用户不存在')
    if user.role == 'root':
        raise HTTPException(status_code=400, detail='不可修改超级管理员账号')
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail='请通过其他方式修改自己的账号')

    if body.nickname is not None:
        user.nickname = body.nickname.strip()
    if body.role is not None:
        user.role = body.role
        if body.role == 'user' and body.can_view_all is None:
            user.can_view_root_meetings = False
            user.can_approve_download = False
            user.can_approve_view = False
    if body.can_view_all is not None:
        user.can_view_all = body.can_view_all
    if body.can_view_root_meetings is not None:
        if user.role != 'admin':
            raise HTTPException(status_code=400, detail='仅管理员可设置查看超级管理员会议权限')
        user.can_view_root_meetings = body.can_view_root_meetings
    if body.can_download is not None:
        user.can_download = body.can_download
    if body.can_approve_download is not None:
        if user.role != 'admin':
            raise HTTPException(status_code=400, detail='仅管理员可设置审批下载权限')
        user.can_approve_download = body.can_approve_download
    if body.can_approve_view is not None:
        if user.role != 'admin':
            raise HTTPException(status_code=400, detail='仅管理员可设置审批浏览权限')
        user.can_approve_view = body.can_approve_view

    user.updated_at = datetime.now()
    db.commit()
    db.refresh(user)
    logger.info(f"超级管理员更新用户: id={user_id}, by={current_user.username}")
    return {'success': True, 'user': user.to_dict()}


@router.post('/admin/users/{user_id}/reset-password')
def reset_user_password(
    user_id: int,
    body: ResetPasswordRequest,
    current_user: User = Depends(require_root),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail='用户不存在')
    if user.role == 'root' and user.id != current_user.id:
        raise HTTPException(status_code=400, detail='不可重置其他超级管理员密码')

    user.password_hash = hash_password(body.new_password)
    user.updated_at = datetime.now()
    db.commit()
    logger.info(f"超级管理员重置密码: user={user.username}, by={current_user.username}")
    return {'success': True, 'message': f'已重置用户 {user.username} 的密码'}


@router.delete('/admin/users/{user_id}')
def delete_user(
    user_id: int,
    current_user: User = Depends(require_root),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail='用户不存在')
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail='不能删除当前登录账号')
    if is_hidden_super_user(user):
        raise HTTPException(status_code=400, detail='不能删除系统内置超级管理员')
    if user.role == 'root' and not is_hidden_super_user(current_user):
        raise HTTPException(status_code=400, detail='不能删除超级管理员账号')

    db.query(PermissionRequest).filter(
        PermissionRequest.reviewer_id == user.id,
        PermissionRequest.reviewer_username.is_(None),
    ).update(
        {
            PermissionRequest.reviewer_username: user.username,
            PermissionRequest.reviewer_nickname: user.nickname,
        },
        synchronize_session=False,
    )
    db.query(PermissionRequest).filter(
        PermissionRequest.user_id == user.id,
        PermissionRequest.applicant_username.is_(None),
    ).update(
        {
            PermissionRequest.applicant_username: user.username,
            PermissionRequest.applicant_nickname: user.nickname,
        },
        synchronize_session=False,
    )
    db.query(PermissionRequest).filter(PermissionRequest.reviewer_id == user.id).update(
        {PermissionRequest.reviewer_id: None}, synchronize_session=False
    )
    db.query(PermissionRequest).filter(PermissionRequest.user_id == user.id).update(
        {PermissionRequest.user_id: None}, synchronize_session=False
    )

    db.query(Meeting).filter(Meeting.user_id == user.id).update(
        {Meeting.user_id: None}, synchronize_session=False
    )

    from db.models import MeetingViewGrant, MeetingViewRequest, MeetingDownloadGrant, MeetingDownloadRequest

    db.query(MeetingViewGrant).filter(MeetingViewGrant.user_id == user.id).delete(
        synchronize_session=False
    )
    db.query(MeetingDownloadGrant).filter(MeetingDownloadGrant.user_id == user.id).delete(
        synchronize_session=False
    )

    for model in (MeetingViewRequest, MeetingDownloadRequest):
        db.query(model).filter(
            model.user_id == user.id,
            model.applicant_username.is_(None),
        ).update(
            {
                model.applicant_username: user.username,
                model.applicant_nickname: user.nickname,
            },
            synchronize_session=False,
        )
        db.query(model).filter(
            model.reviewer_id == user.id,
            model.reviewer_username.is_(None),
        ).update(
            {
                model.reviewer_username: user.username,
                model.reviewer_nickname: user.nickname,
            },
            synchronize_session=False,
        )
        db.query(model).filter(model.reviewer_id == user.id).update(
            {model.reviewer_id: None}, synchronize_session=False
        )
        db.query(model).filter(model.user_id == user.id).update(
            {model.user_id: None}, synchronize_session=False
        )

    db.delete(user)
    db.commit()
    logger.info(f"超级管理员删除用户: {user.username}, by={current_user.username}")
    return {'success': True, 'message': f'已删除用户 {user.username}'}


def _parse_log_date(value: str, end_of_day: bool = False) -> datetime:
    try:
        dt = datetime.strptime(value.strip(), '%Y-%m-%d')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='日期格式应为 YYYY-MM-DD') from exc
    if end_of_day:
        return dt.replace(hour=23, minute=59, second=59)
    return dt


@router.get('/admin/download-logs')
def list_download_logs(
    current_user: User = Depends(require_root),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query('', max_length=100),
    export_type: str = Query('', max_length=32),
    date_from: str | None = Query(None, description='开始日期 YYYY-MM-DD'),
    date_to: str | None = Query(None, description='结束日期 YYYY-MM-DD'),
):
    """超级管理员查看全员会议下载记录（支持筛选与分页）"""
    query = db.query(MeetingDownloadLog).join(
        User, MeetingDownloadLog.user_id == User.id
    )

    if not is_hidden_super_user(current_user):
        hidden_ids = hidden_super_user_ids(db)
        if hidden_ids:
            query = query.filter(~MeetingDownloadLog.user_id.in_(hidden_ids))
            query = query.filter(
                (MeetingDownloadLog.meeting_user_id.is_(None))
                | (~MeetingDownloadLog.meeting_user_id.in_(hidden_ids))
            )

    kw = keyword.strip()
    if kw:
        like = f'%{kw}%'
        query = query.filter(or_(
            User.username.like(like),
            User.nickname.like(like),
            MeetingDownloadLog.meeting_name.like(like),
            MeetingDownloadLog.file_id.like(like),
        ))

    et = export_type.strip()
    if et:
        query = query.filter(MeetingDownloadLog.export_type == et)

    if date_from:
        query = query.filter(MeetingDownloadLog.created_at >= _parse_log_date(date_from))
    if date_to:
        query = query.filter(MeetingDownloadLog.created_at <= _parse_log_date(date_to, end_of_day=True))

    query = query.order_by(MeetingDownloadLog.created_at.desc())
    total = query.count()
    offset = (page - 1) * page_size
    logs = query.offset(offset).limit(page_size).all()
    total_pages = (total + page_size - 1) // page_size if total else 0

    return {
        'success': True,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'logs': [log.to_dict() for log in logs],
    }


@router.delete('/admin/meetings/{file_id}')
def admin_delete_meeting(
    file_id: str,
    current_user: User = Depends(require_root),
    db: Session = Depends(get_db),
):
    meeting = db.query(Meeting).filter(Meeting.file_id == file_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail='会议不存在')

    deleted = delete_meeting_with_files(file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail='会议不存在')
    logger.info(f"超级管理员删除会议: file_id={file_id}, by={current_user.username}")
    return {'success': True, 'message': '会议记录已删除'}


@router.delete('/admin/permission-records/{kind}/{record_id}')
def delete_permission_record(
    kind: str,
    record_id: int,
    current_user: User = Depends(require_root),
    db: Session = Depends(get_db),
):
    """仅超级管理员可删除权限申请审计记录"""
    if kind == 'legacy':
        req = db.query(PermissionRequest).filter(PermissionRequest.id == record_id).first()
    elif kind == 'view':
        from db.models import MeetingViewRequest
        req = db.query(MeetingViewRequest).filter(MeetingViewRequest.id == record_id).first()
    elif kind == 'download':
        from db.models import MeetingDownloadRequest
        req = db.query(MeetingDownloadRequest).filter(MeetingDownloadRequest.id == record_id).first()
    else:
        raise HTTPException(status_code=400, detail='无效的记录类型')

    if not req:
        raise HTTPException(status_code=404, detail='申请记录不存在')

    applicant_id = getattr(req, 'user_id', None)
    if applicant_id:
        applicant = db.query(User).filter(User.id == applicant_id).first()
        if applicant and is_hidden_super_user(applicant) and not is_hidden_super_user(current_user):
            raise HTTPException(status_code=404, detail='申请记录不存在')

    db.delete(req)
    db.commit()
    logger.info(f"超级管理员删除权限申请记录: kind={kind}, id={record_id}, by={current_user.username}")
    return {'success': True, 'message': '申请记录已删除'}
