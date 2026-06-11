from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.schemas import PageResult, ResponseBase
from app.schemas.user import (
    AccessReviewAction,
    SystemSettingOut,
    ViewAccessRequestCreate,
    ViewAccessRequestOut,
)
from app.services.permission_service import PermissionService

router = APIRouter(prefix="/permissions", tags=["权限管理"])


@router.post("/access-requests", response_model=ResponseBase[ViewAccessRequestOut], status_code=status.HTTP_201_CREATED)
def submit_access_request(db: DbSession, user: CurrentUser, data: ViewAccessRequestCreate):
    try:
        req = PermissionService.create_access_request(db, user, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(
        data=ViewAccessRequestOut(
            id=req.id,
            user_id=req.user_id,
            request_type=req.request_type,
            status=req.status,
            reason=req.reason,
            reviewer_id=req.reviewer_id,
            review_note=req.review_note,
            created_at=req.created_at,
            reviewed_at=req.reviewed_at,
            username=user.username,
            nickname=user.nickname,
        ),
        message="申请已提交",
    )


@router.get("/access-requests/types", response_model=ResponseBase[list])
def list_applicable_request_types(user: CurrentUser):
    return ResponseBase(data=PermissionService.list_request_types_for_user(user))


@router.get("/access-requests/stats", response_model=ResponseBase[dict])
def access_request_stats(db: DbSession, user: CurrentUser):
    return ResponseBase(data=PermissionService.get_access_request_stats(db, user))


@router.get("/access-requests", response_model=ResponseBase[PageResult[ViewAccessRequestOut]])
def list_access_requests(
    db: DbSession,
    user: CurrentUser,
    status: str | None = None,
    request_type: str | None = None,
    scope: str | None = Query(
        None,
        description="mine=仅我的申请；review=待我审批范围（审核员）。默认：审核员为 review，普通用户为 mine",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    items, total = PermissionService.list_access_requests(
        db, user, status, request_type, page, page_size, scope=scope
    )
    return ResponseBase(
        data=PageResult(
            items=[ViewAccessRequestOut(**i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post("/access-requests/{request_id}/review", response_model=ResponseBase[ViewAccessRequestOut])
def review_access_request(
    db: DbSession,
    reviewer: AdminUser,
    request_id: int,
    data: AccessReviewAction,
):
    try:
        req = PermissionService.review_access_request(
            db, request_id, reviewer, data.approve, data.review_note
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    from app.models import User

    applicant = db.query(User).filter(User.id == req.user_id).first()
    reviewer = db.query(User).filter(User.id == req.reviewer_id).first() if req.reviewer_id else None
    return ResponseBase(
        data=ViewAccessRequestOut(
            id=req.id,
            user_id=req.user_id,
            request_type=req.request_type,
            status=req.status,
            reason=req.reason,
            reviewer_id=req.reviewer_id,
            review_note=req.review_note,
            created_at=req.created_at,
            reviewed_at=req.reviewed_at,
            username=applicant.username if applicant else None,
            nickname=applicant.nickname if applicant else None,
            reviewer_username=reviewer.username if reviewer else None,
            reviewer_nickname=reviewer.nickname if reviewer else None,
        ),
        message="已通过申请" if data.approve else "已拒绝申请",
    )


@router.post("/users/{user_id}/revoke-library", response_model=ResponseBase[dict])
def revoke_library_access(db: DbSession, reviewer: AdminUser, user_id: int):
    try:
        user = PermissionService.revoke_library_access(db, user_id, reviewer)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(data={"user_id": user.id, "view_library": bool(user.view_library)})


@router.get("/settings", response_model=ResponseBase[SystemSettingOut])
def get_permission_settings(db: DbSession, user: CurrentUser):
    return ResponseBase(data=SystemSettingOut(**PermissionService.get_settings(db)))


@router.put("/settings", response_model=ResponseBase[SystemSettingOut])
def update_permission_settings(
    db: DbSession,
    reviewer: AdminUser,
    block_upper_role_tasks: bool = Query(...),
):
    try:
        settings = PermissionService.update_settings(db, reviewer, block_upper_role_tasks)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(data=SystemSettingOut(**settings), message="设置已更新")
