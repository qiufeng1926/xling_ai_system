"""单条会议浏览/下载权限申请与审批"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth_utils import get_current_user, get_db
from api.permissions import (
    can_access_meeting,
    can_approve_download_requests,
    can_download_files,
    can_download_meeting,
)
from db.models import (
    Meeting,
    MeetingDownloadGrant,
    MeetingDownloadRequest,
    MeetingViewGrant,
    MeetingViewRequest,
    User,
)
from utils.hidden_user import hidden_super_user_ids, is_hidden_super_user

router = APIRouter()


class MeetingAccessApplyRequest(BaseModel):
    file_ids: list[str] = Field(..., min_length=1, max_length=50)
    reason: str = Field(default='', max_length=500)


class MeetingAccessReviewRequest(BaseModel):
    action: str = Field(..., pattern='^(approve|reject)$')
    review_note: str = Field(default='', max_length=500)


class MeetingPermissionBatchReviewRequest(BaseModel):
    kind: str = Field(..., pattern='^(view|download)$')
    request_ids: list[int] = Field(..., min_length=1, max_length=100)
    action: str = Field(..., pattern='^(approve|reject)$')
    review_note: str = Field(default='', max_length=500)


def _require_root(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_root():
        raise HTTPException(status_code=403, detail='仅超级管理员可执行此操作')
    return current_user


def _require_download_reviewer(current_user: User = Depends(get_current_user)) -> User:
    if not can_approve_download_requests(current_user):
        raise HTTPException(status_code=403, detail='无权审批会议下载申请')
    return current_user


def _meeting_display_name(meeting: Meeting) -> str:
    return meeting.meeting_name or meeting.original_filename or '未命名会议'


def _filter_hidden_applicant_ids(db: Session, viewer: User) -> list[int] | None:
    if is_hidden_super_user(viewer):
        return None
    hidden_ids = hidden_super_user_ids(db)
    return hidden_ids or None


def _filter_view_query(db: Session, viewer: User, query):
    hidden_ids = _filter_hidden_applicant_ids(db, viewer)
    if hidden_ids:
        query = query.filter(~MeetingViewRequest.user_id.in_(hidden_ids))
    return query


def _filter_download_query(db: Session, viewer: User, query):
    hidden_ids = _filter_hidden_applicant_ids(db, viewer)
    if hidden_ids:
        query = query.filter(~MeetingDownloadRequest.user_id.in_(hidden_ids))
    return query


def _get_meeting_owner(db: Session, meeting: Meeting) -> User | None:
    if not meeting.user_id:
        return None
    return db.query(User).filter(User.id == meeting.user_id).first()


def _approve_view_request(req: MeetingViewRequest, reviewer: User, applicant: User, db: Session) -> None:
    req.status = 'approved'
    existing = (
        db.query(MeetingViewGrant)
        .filter(
            MeetingViewGrant.user_id == req.user_id,
            MeetingViewGrant.file_id == req.file_id,
        )
        .first()
    )
    if not existing:
        db.add(
            MeetingViewGrant(
                user_id=req.user_id,
                username=applicant.username,
                file_id=req.file_id,
                granted_by=reviewer.id,
            )
        )
    elif not existing.username and applicant.username:
        existing.username = applicant.username


def _approve_download_request(req: MeetingDownloadRequest, reviewer: User, applicant: User, db: Session) -> None:
    req.status = 'approved'
    existing = (
        db.query(MeetingDownloadGrant)
        .filter(
            MeetingDownloadGrant.user_id == req.user_id,
            MeetingDownloadGrant.file_id == req.file_id,
        )
        .first()
    )
    if not existing:
        db.add(
            MeetingDownloadGrant(
                user_id=req.user_id,
                username=applicant.username,
                file_id=req.file_id,
                granted_by=reviewer.id,
            )
        )
    elif not existing.username and applicant.username:
        existing.username = applicant.username


def _review_view_request(
    request_id: int,
    action: str,
    review_note: str | None,
    reviewer: User,
    db: Session,
) -> MeetingViewRequest:
    req = db.query(MeetingViewRequest).filter(MeetingViewRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail='申请不存在')
    if req.status != 'pending':
        raise HTTPException(status_code=400, detail='该申请已处理')

    applicant = db.query(User).filter(User.id == req.user_id).first()
    if not applicant:
        raise HTTPException(status_code=404, detail='申请人不存在')
    if is_hidden_super_user(applicant) and not is_hidden_super_user(reviewer):
        raise HTTPException(status_code=404, detail='申请不存在')

    req.reviewer_id = reviewer.id
    req.review_note = review_note
    req.reviewed_at = datetime.now()

    if action == 'approve':
        _approve_view_request(req, reviewer, applicant, db)
    else:
        req.status = 'rejected'

    db.commit()
    db.refresh(req)
    return req


def _review_download_request(
    request_id: int,
    action: str,
    review_note: str | None,
    reviewer: User,
    db: Session,
) -> MeetingDownloadRequest:
    req = db.query(MeetingDownloadRequest).filter(MeetingDownloadRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail='申请不存在')
    if req.status != 'pending':
        raise HTTPException(status_code=400, detail='该申请已处理')

    applicant = db.query(User).filter(User.id == req.user_id).first()
    if not applicant:
        raise HTTPException(status_code=404, detail='申请人不存在')
    if is_hidden_super_user(applicant) and not is_hidden_super_user(reviewer):
        raise HTTPException(status_code=404, detail='申请不存在')

    req.reviewer_id = reviewer.id
    req.review_note = review_note
    req.reviewed_at = datetime.now()

    if action == 'approve':
        _approve_download_request(req, reviewer, applicant, db)
    else:
        req.status = 'rejected'

    db.commit()
    db.refresh(req)
    return req


@router.post('/meetings/access-requests')
def apply_meeting_view_access(
    body: MeetingAccessApplyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.is_root():
        raise HTTPException(status_code=400, detail='超级管理员无需申请浏览权限')
    if current_user.can_view_all_meetings():
        raise HTTPException(status_code=400, detail='您已拥有浏览他人会议的权限')

    reason = body.reason.strip() or None
    seen: set[str] = set()
    created: list[dict] = []
    skipped: list[dict] = []

    for raw_file_id in body.file_ids:
        file_id = (raw_file_id or '').strip()
        if not file_id or file_id in seen:
            continue
        seen.add(file_id)

        meeting = db.query(Meeting).filter(Meeting.file_id == file_id).first()
        if not meeting:
            skipped.append({'file_id': file_id, 'reason': '会议不存在'})
            continue

        owner = _get_meeting_owner(db, meeting)
        if can_access_meeting(current_user, meeting, owner, session=db):
            skipped.append({'file_id': file_id, 'reason': '您已有权浏览该会议'})
            continue

        pending = (
            db.query(MeetingViewRequest)
            .filter(
                MeetingViewRequest.user_id == current_user.id,
                MeetingViewRequest.file_id == file_id,
                MeetingViewRequest.status == 'pending',
            )
            .first()
        )
        if pending:
            skipped.append({'file_id': file_id, 'reason': '该会议已有待审批浏览申请'})
            continue

        req = MeetingViewRequest(
            user_id=current_user.id,
            file_id=file_id,
            meeting_name=_meeting_display_name(meeting),
            reason=reason,
            status='pending',
        )
        db.add(req)
        db.flush()
        created.append(req.to_dict())

    if not created:
        detail = skipped[0]['reason'] if len(skipped) == 1 else '没有可提交的申请'
        raise HTTPException(status_code=400, detail=detail)

    db.commit()
    return {
        'success': True,
        'created': created,
        'skipped': skipped,
        'message': f'已提交 {len(created)} 条会议浏览申请',
    }


@router.post('/meetings/download-requests')
def apply_meeting_download_access(
    body: MeetingAccessApplyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.is_root():
        raise HTTPException(status_code=400, detail='超级管理员默认可下载，无需申请')
    if current_user.can_download_files():
        raise HTTPException(status_code=400, detail='您已拥有会议下载/导出权限')

    reason = body.reason.strip() or None
    seen: set[str] = set()
    created: list[dict] = []
    skipped: list[dict] = []

    for raw_file_id in body.file_ids:
        file_id = (raw_file_id or '').strip()
        if not file_id or file_id in seen:
            continue
        seen.add(file_id)

        meeting = db.query(Meeting).filter(Meeting.file_id == file_id).first()
        if not meeting:
            skipped.append({'file_id': file_id, 'reason': '会议不存在'})
            continue

        owner = _get_meeting_owner(db, meeting)
        if not can_access_meeting(current_user, meeting, owner, session=db):
            skipped.append({'file_id': file_id, 'reason': '请先获得该会议的浏览权限'})
            continue
        if can_download_meeting(current_user, meeting, owner, session=db):
            skipped.append({'file_id': file_id, 'reason': '您已有权下载该会议'})
            continue

        pending = (
            db.query(MeetingDownloadRequest)
            .filter(
                MeetingDownloadRequest.user_id == current_user.id,
                MeetingDownloadRequest.file_id == file_id,
                MeetingDownloadRequest.status == 'pending',
            )
            .first()
        )
        if pending:
            skipped.append({'file_id': file_id, 'reason': '该会议已有待审批下载申请'})
            continue

        req = MeetingDownloadRequest(
            user_id=current_user.id,
            file_id=file_id,
            meeting_name=_meeting_display_name(meeting),
            reason=reason,
            status='pending',
        )
        db.add(req)
        db.flush()
        created.append(req.to_dict())

    if not created:
        detail = skipped[0]['reason'] if len(skipped) == 1 else '没有可提交的申请'
        raise HTTPException(status_code=400, detail=detail)

    db.commit()
    return {
        'success': True,
        'created': created,
        'skipped': skipped,
        'message': f'已提交 {len(created)} 条会议下载申请',
    }


@router.get('/meetings/access-requests/mine')
def list_my_meeting_view_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
):
    query = db.query(MeetingViewRequest).filter(MeetingViewRequest.user_id == current_user.id)
    if status:
        query = query.filter(MeetingViewRequest.status == status)
    rows = query.order_by(MeetingViewRequest.created_at.desc()).limit(limit).all()
    return {'success': True, 'requests': [row.to_dict() for row in rows]}


@router.get('/meetings/download-requests/mine')
def list_my_meeting_download_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
):
    query = db.query(MeetingDownloadRequest).filter(MeetingDownloadRequest.user_id == current_user.id)
    if status:
        query = query.filter(MeetingDownloadRequest.status == status)
    rows = query.order_by(MeetingDownloadRequest.created_at.desc()).limit(limit).all()
    return {'success': True, 'requests': [row.to_dict() for row in rows]}


@router.get('/meetings/access-requests/stats')
def meeting_permission_request_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    view_my_pending = (
        db.query(MeetingViewRequest)
        .filter(
            MeetingViewRequest.user_id == current_user.id,
            MeetingViewRequest.status == 'pending',
        )
        .count()
    )
    download_my_pending = (
        db.query(MeetingDownloadRequest)
        .filter(
            MeetingDownloadRequest.user_id == current_user.id,
            MeetingDownloadRequest.status == 'pending',
        )
        .count()
    )
    view_pending_for_review = 0
    download_pending_for_review = 0
    if current_user.is_root():
        view_q = db.query(MeetingViewRequest).filter(MeetingViewRequest.status == 'pending')
        view_pending_for_review = _filter_view_query(db, current_user, view_q).count()
    if can_approve_download_requests(current_user):
        download_q = db.query(MeetingDownloadRequest).filter(MeetingDownloadRequest.status == 'pending')
        download_pending_for_review = _filter_download_query(db, current_user, download_q).count()

    my_pending = view_my_pending + download_my_pending
    pending_for_review = view_pending_for_review + download_pending_for_review
    return {
        'success': True,
        'my_pending': my_pending,
        'pending_for_review': pending_for_review,
        'view': {
            'my_pending': view_my_pending,
            'pending_for_review': view_pending_for_review,
        },
        'download': {
            'my_pending': download_my_pending,
            'pending_for_review': download_pending_for_review,
        },
    }


@router.get('/meetings/access-requests/pending')
def list_pending_meeting_view_requests(
    current_user: User = Depends(_require_root),
    db: Session = Depends(get_db),
    status: str = Query('pending'),
    limit: int = Query(100, ge=1, le=200),
):
    query = db.query(MeetingViewRequest)
    if status:
        query = query.filter(MeetingViewRequest.status == status)
    query = _filter_view_query(db, current_user, query)
    rows = query.order_by(MeetingViewRequest.created_at.asc()).limit(limit).all()
    return {'success': True, 'requests': [row.to_dict() for row in rows]}


@router.get('/meetings/download-requests/pending')
def list_pending_meeting_download_requests(
    current_user: User = Depends(_require_download_reviewer),
    db: Session = Depends(get_db),
    status: str = Query('pending'),
    limit: int = Query(100, ge=1, le=200),
):
    query = db.query(MeetingDownloadRequest)
    if status:
        query = query.filter(MeetingDownloadRequest.status == status)
    query = _filter_download_query(db, current_user, query)
    rows = query.order_by(MeetingDownloadRequest.created_at.asc()).limit(limit).all()
    return {'success': True, 'requests': [row.to_dict() for row in rows]}


@router.post('/meetings/access-requests/{request_id}/review')
def review_meeting_view_request(
    request_id: int,
    body: MeetingAccessReviewRequest,
    current_user: User = Depends(_require_root),
    db: Session = Depends(get_db),
):
    req = _review_view_request(
        request_id,
        body.action,
        body.review_note.strip() or None,
        current_user,
        db,
    )
    return {'success': True, 'request': req.to_dict()}


@router.post('/meetings/download-requests/{request_id}/review')
def review_meeting_download_request(
    request_id: int,
    body: MeetingAccessReviewRequest,
    current_user: User = Depends(_require_download_reviewer),
    db: Session = Depends(get_db),
):
    req = _review_download_request(
        request_id,
        body.action,
        body.review_note.strip() or None,
        current_user,
        db,
    )
    return {'success': True, 'request': req.to_dict()}


@router.post('/meetings/permission-requests/batch-review')
def batch_review_meeting_permission_requests(
    body: MeetingPermissionBatchReviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.kind == 'view':
        if not current_user.is_root():
            raise HTTPException(status_code=403, detail='仅超级管理员可审批浏览申请')
    elif not can_approve_download_requests(current_user):
        raise HTTPException(status_code=403, detail='无权审批会议下载申请')

    review_note = body.review_note.strip() or None
    reviewed: list[dict] = []
    errors: list[dict] = []

    for request_id in body.request_ids:
        try:
            if body.kind == 'view':
                req = _review_view_request(request_id, body.action, review_note, current_user, db)
            else:
                req = _review_download_request(request_id, body.action, review_note, current_user, db)
            reviewed.append(req.to_dict())
        except HTTPException as exc:
            errors.append({'request_id': request_id, 'reason': exc.detail})

    if not reviewed:
        detail = errors[0]['reason'] if len(errors) == 1 else '批量审批失败'
        raise HTTPException(status_code=400, detail=detail)

    return {
        'success': True,
        'reviewed': reviewed,
        'errors': errors,
        'message': f'已处理 {len(reviewed)} 条申请',
    }
