from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession, SuperAdminUser
from app.models.offboarding import UserOffboardingRecord
from app.schemas import PageResult, ResponseBase
from app.schemas.offboarding import OffboardingApplyRequest, OffboardingCompleteRequest, OffboardingRecordOut
from app.services.offboarding_service import OffboardingService

router = APIRouter(prefix="/offboarding", tags=["离职交接"])


def _record_to_out(db, record: UserOffboardingRecord) -> OffboardingRecordOut:
    return OffboardingRecordOut(**OffboardingService._record_out(db, record))


@router.post("/apply", response_model=ResponseBase[OffboardingRecordOut])
def apply_offboarding(db: DbSession, user: CurrentUser, data: OffboardingApplyRequest):
    try:
        record = OffboardingService.apply(
            db,
            user,
            reason=data.reason,
            last_work_day=data.last_work_day,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(data=_record_to_out(db, record), message="离职申请已提交")


@router.get("/my", response_model=ResponseBase[OffboardingRecordOut | None])
def my_offboarding(db: DbSession, user: CurrentUser):
    record = OffboardingService.get_my_pending(db, user)
    if not record:
        return ResponseBase(data=None)
    return ResponseBase(data=_record_to_out(db, record))


@router.get("", response_model=ResponseBase[PageResult[OffboardingRecordOut]])
def list_offboarding(
    db: DbSession,
    _: SuperAdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
):
    items, total = OffboardingService.list_records(db, page=page, page_size=page_size, status=status)
    return ResponseBase(
        data=PageResult(
            items=[OffboardingRecordOut(**item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{record_id}", response_model=ResponseBase[OffboardingRecordOut])
def get_offboarding(db: DbSession, _: SuperAdminUser, record_id: int):
    record = OffboardingService.get_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    return ResponseBase(data=_record_to_out(db, record))


@router.post("/{record_id}/complete", response_model=ResponseBase[OffboardingRecordOut])
def complete_offboarding(
    db: DbSession,
    operator: SuperAdminUser,
    record_id: int,
    data: OffboardingCompleteRequest,
):
    try:
        record = OffboardingService.complete(
            db,
            record_id,
            operator,
            handover_user_id=data.handover_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(data=_record_to_out(db, record), message="离职交接已完成")


@router.post("/{record_id}/cancel", response_model=ResponseBase[OffboardingRecordOut])
def cancel_offboarding(db: DbSession, operator: SuperAdminUser, record_id: int):
    try:
        record = OffboardingService.cancel(db, record_id, operator)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(data=_record_to_out(db, record), message="离职申请已取消")


@router.post("/rehire/{user_id}", response_model=ResponseBase[dict])
def rehire_user(db: DbSession, operator: SuperAdminUser, user_id: int):
    try:
        user = OffboardingService.rehire(db, user_id, operator)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(
        data={"id": user.id, "username": user.username, "account_status": user.account_status},
        message="账号已重新开通",
    )
