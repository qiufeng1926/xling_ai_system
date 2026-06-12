"""
用户认证与权限申请 API
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from utils.password import hash_password, verify_password
from api.auth_utils import create_access_token, get_current_user, get_db
from api.permissions import can_approve_download_requests
from db.models import PermissionRequest, User
from db.session import seed_default_users
from utils.logger import get_logger
from utils.hidden_user import hidden_super_user_ids, is_hidden_super_user

router = APIRouter()
logger = get_logger("auth_route")


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    nickname: str = Field(..., min_length=1, max_length=32)
    password: str = Field(..., min_length=6, max_length=64)


class LoginRequest(BaseModel):
    username: str
    password: str


class PermissionApplyRequest(BaseModel):
    request_type: str = Field(..., pattern='^(view_all|admin|view_root_meetings|download)$')
    reason: str = Field(default='', max_length=500)


class PermissionReviewRequest(BaseModel):
    action: str = Field(..., pattern='^(approve|reject)$')
    review_note: str = Field(default='', max_length=500)


def _user_response(user: User, token: str | None = None) -> dict:
    data = {
        'success': True,
        'user': user.to_dict(),
    }
    if token:
        data['token'] = token
    return data


@router.post('/auth/register')
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    username = body.username.strip()
    nickname = body.nickname.strip()
    if username in ('root', 'admin', 'qiufengai'):
        raise HTTPException(status_code=400, detail='该用户名不可注册')
    if not nickname:
        raise HTTPException(status_code=400, detail='昵称不能为空')

    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail='用户名已存在')

    user = User(
        username=username,
        nickname=nickname,
        password_hash=hash_password(body.password),
        role='user',
        can_view_all=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, user.username, user.role)
    logger.info(f"用户注册成功: {username}")
    return _user_response(user, token)


@router.post('/auth/login')
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username.strip()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail='用户名或密码错误')

    token = create_access_token(user.id, user.username, user.role)
    logger.info(f"用户登录: {user.username}")
    return _user_response(user, token)


@router.get('/auth/me')
def get_me(current_user: User = Depends(get_current_user)):
    return {'success': True, 'user': current_user.to_dict()}


@router.post('/auth/requests')
def apply_permission(
    body: PermissionApplyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.request_type == 'admin' and current_user.is_admin():
        raise HTTPException(status_code=400, detail='您已是管理员')

    if body.request_type == 'view_all' and current_user.can_view_all_meetings():
        raise HTTPException(status_code=400, detail='您已拥有查看全部会议的权限')

    if body.request_type == 'view_root_meetings':
        if current_user.role != 'admin':
            raise HTTPException(status_code=400, detail='仅管理员可申请查看超级管理员会议')
        if current_user.can_view_root_meetings:
            raise HTTPException(status_code=400, detail='您已拥有查看超级管理员会议的权限')

    if body.request_type == 'download':
        if current_user.is_root():
            raise HTTPException(status_code=400, detail='超级管理员默认可下载，无需申请')
        if current_user.can_download_files():
            raise HTTPException(status_code=400, detail='您已拥有下载/导出权限')

    pending = db.query(PermissionRequest).filter(
        PermissionRequest.user_id == current_user.id,
        PermissionRequest.request_type == body.request_type,
        PermissionRequest.status == 'pending',
    ).first()
    if pending:
        raise HTTPException(status_code=400, detail='已有待审批的同类申请，请等待处理')

    req = PermissionRequest(
        user_id=current_user.id,
        request_type=body.request_type,
        reason=body.reason.strip() or None,
        status='pending',
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return {'success': True, 'request': req.to_dict()}


@router.get('/auth/requests/mine')
def list_my_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    requests = (
        db.query(PermissionRequest)
        .filter(PermissionRequest.user_id == current_user.id)
        .order_by(PermissionRequest.created_at.desc())
        .all()
    )
    return {'success': True, 'requests': [r.to_dict() for r in requests]}


@router.get('/auth/requests/pending')
def list_pending_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.is_admin() and not current_user.is_root():
        raise HTTPException(status_code=403, detail='无权查看审批列表')

    if current_user.is_root():
        query = (
            db.query(PermissionRequest)
            .join(User, PermissionRequest.user_id == User.id)
            .filter(
                PermissionRequest.status == 'pending',
                or_(
                    and_(User.role == 'user', PermissionRequest.request_type == 'admin'),
                    and_(User.role == 'admin', PermissionRequest.request_type == 'view_root_meetings'),
                    and_(User.role != 'root', PermissionRequest.request_type == 'download'),
                ),
            )
        )
    elif current_user.is_admin():
        pending_filters = [
            and_(User.role == 'user', PermissionRequest.request_type == 'view_all'),
        ]
        if current_user.can_approve_download_requests():
            pending_filters.append(
                and_(User.role != 'root', PermissionRequest.request_type == 'download'),
            )
        query = (
            db.query(PermissionRequest)
            .join(User, PermissionRequest.user_id == User.id)
            .filter(
                PermissionRequest.status == 'pending',
                or_(*pending_filters),
            )
        )
    else:
        raise HTTPException(status_code=403, detail='无权查看审批列表')

    if not is_hidden_super_user(current_user):
        hidden_ids = hidden_super_user_ids(db)
        if hidden_ids:
            query = query.filter(~PermissionRequest.user_id.in_(hidden_ids))

    requests = query.order_by(PermissionRequest.created_at.asc()).all()
    return {'success': True, 'requests': [r.to_dict() for r in requests]}


@router.get('/auth/requests/review-history')
def list_admin_review_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 100,
):
    """超级管理员查看管理员已处理的审批记录（查看全部会议等）"""
    if not current_user.is_root():
        raise HTTPException(status_code=403, detail='仅超级管理员可查看审批记录')

    requests = (
        db.query(PermissionRequest)
        .join(User, PermissionRequest.user_id == User.id)
        .filter(
            PermissionRequest.request_type == 'view_all',
            PermissionRequest.status.in_(('approved', 'rejected')),
            PermissionRequest.reviewer_id.isnot(None),
        )
        .order_by(PermissionRequest.reviewed_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    if not is_hidden_super_user(current_user):
        hidden_ids = set(hidden_super_user_ids(db))
        if hidden_ids:
            requests = [r for r in requests if r.user_id not in hidden_ids]
    return {'success': True, 'requests': [r.to_dict() for r in requests]}


@router.post('/auth/requests/{request_id}/review')
def review_request(
    request_id: int,
    body: PermissionReviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req = db.query(PermissionRequest).filter(PermissionRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail='申请不存在')
    if req.status != 'pending':
        raise HTTPException(status_code=400, detail='该申请已处理')

    if req.request_type == 'view_all':
        if not current_user.is_admin():
            raise HTTPException(status_code=403, detail='仅管理员可审批查看权限申请')
    elif req.request_type == 'admin':
        if not current_user.is_root():
            raise HTTPException(status_code=403, detail='仅超级管理员可审批管理员申请')
    elif req.request_type == 'view_root_meetings':
        if not current_user.is_root():
            raise HTTPException(status_code=403, detail='仅超级管理员可审批该申请')
    elif req.request_type == 'download':
        if not can_approve_download_requests(current_user):
            raise HTTPException(status_code=403, detail='无权审批下载权限申请')
    else:
        raise HTTPException(status_code=400, detail='未知申请类型')

    applicant = db.query(User).filter(User.id == req.user_id).first()
    if not applicant:
        raise HTTPException(status_code=404, detail='申请人不存在')
    if is_hidden_super_user(applicant) and not is_hidden_super_user(current_user):
        raise HTTPException(status_code=404, detail='申请不存在')

    req.reviewer_id = current_user.id
    req.review_note = body.review_note.strip() or None
    req.reviewed_at = datetime.now()

    if body.action == 'approve':
        req.status = 'approved'
        if req.request_type == 'view_all':
            applicant.can_view_all = True
        elif req.request_type == 'admin':
            applicant.role = 'admin'
            applicant.can_view_all = True
        elif req.request_type == 'view_root_meetings':
            applicant.can_view_root_meetings = True
        elif req.request_type == 'download':
            applicant.can_download = True
    else:
        req.status = 'rejected'

    db.commit()
    db.refresh(req)
    logger.info(
        f"权限申请已{req.status}: id={request_id}, reviewer={current_user.username}"
    )
    return {'success': True, 'request': req.to_dict()}


@router.post('/auth/seed')
def seed_users(db: Session = Depends(get_db)):
    """初始化默认管理员账号（仅在没有用户时可用；密码见 SEED_*_PASSWORD 或服务端日志）"""
    count = db.query(User).count()
    if count > 0:
        raise HTTPException(status_code=400, detail='用户已存在，无需初始化')
    created = seed_default_users(db)
    db.commit()
    return {
        'success': True,
        'message': (
            f"已创建账号: {', '.join(created) or '无新用户'}。"
            "密码来自环境变量 SEED_ROOT_PASSWORD / SEED_ADMIN_PASSWORD，"
            "未配置时见服务端日志中的随机密码。"
        ),
        'users': created,
    }
