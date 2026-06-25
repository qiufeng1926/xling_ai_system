from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, DbSession, SuperAdminUser
from app.models.offboarding import UserOffboardingRecord
from app.schemas import PageResult, ResponseBase
from app.schemas.offboarding import (
    OffboardingApplyRequest,
    OffboardingAssignHandoverRequest,
    OffboardingConfirmHandoverRequest,
    OffboardingRecordOut,
)
from app.services.offboarding_document_service import OffboardingDocumentService
from app.services.offboarding_service import OffboardingService
from app.utils.access_control import can_manage_users

router = APIRouter(prefix="/offboarding", tags=["离职交接"])


def _record_to_out(db, record: UserOffboardingRecord) -> OffboardingRecordOut:
    return OffboardingRecordOut(**OffboardingService._record_out(db, record))


def _get_record_or_404(db, record_id: int) -> UserOffboardingRecord:
    record = OffboardingService.get_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    return record


def _can_access_record(user, record: UserOffboardingRecord) -> bool:
    if user.id in (record.user_id, record.handover_user_id):
        return True
    return can_manage_users(user)


def _can_access_document(user, record: UserOffboardingRecord) -> bool:
    return _can_access_record(user, record)


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
    record = OffboardingService.get_my_active(db, user)
    if not record:
        return ResponseBase(data=None)
    return ResponseBase(data=_record_to_out(db, record))


@router.get("/handover/my", response_model=ResponseBase[list[OffboardingRecordOut]])
def my_handover_tasks(db: DbSession, user: CurrentUser):
    items = OffboardingService.list_handover_tasks(db, user)
    return ResponseBase(data=[OffboardingRecordOut(**item) for item in items])


@router.get("/handover/archive", response_model=ResponseBase[list[OffboardingRecordOut]])
def my_handover_archive(db: DbSession, user: CurrentUser):
    items = OffboardingService.list_handover_archive(db, user)
    return ResponseBase(data=[OffboardingRecordOut(**item) for item in items])


@router.get("/documents/{doc_id}/download")
def download_document(db: DbSession, user: CurrentUser, doc_id: int):
    doc = OffboardingDocumentService.get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    record = _get_record_or_404(db, doc.record_id)
    if not _can_access_document(user, record):
        raise HTTPException(status_code=403, detail="无权下载")
    path = OffboardingDocumentService.resolve_file_path(doc)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        path,
        filename=doc.filename,
        media_type=OffboardingDocumentService.guess_media_type(doc.filename),
    )


@router.get("/{record_id}/documents", response_model=ResponseBase[list])
def list_record_documents(db: DbSession, user: CurrentUser, record_id: int):
    record = _get_record_or_404(db, record_id)
    if not _can_access_record(user, record):
        raise HTTPException(status_code=403, detail="无权查看")
    return ResponseBase(data=OffboardingDocumentService.list_documents(db, record_id))


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
def get_offboarding(db: DbSession, user: CurrentUser, record_id: int):
    record = _get_record_or_404(db, record_id)
    if not _can_access_record(user, record):
        raise HTTPException(status_code=403, detail="无权查看")
    return ResponseBase(data=_record_to_out(db, record))


@router.post("/{record_id}/assign-handover", response_model=ResponseBase[OffboardingRecordOut])
def assign_handover(
    db: DbSession,
    operator: SuperAdminUser,
    record_id: int,
    data: OffboardingAssignHandoverRequest,
):
    try:
        record = OffboardingService.assign_handover(
            db,
            record_id,
            operator,
            handover_user_id=data.handover_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(data=_record_to_out(db, record), message="已指定交接人，等待员工上传交接文档")


@router.post("/{record_id}/submit-documents", response_model=ResponseBase[OffboardingRecordOut])
async def submit_documents(
    db: DbSession,
    user: CurrentUser,
    record_id: int,
    note: str | None = Form(None),
    files: list[UploadFile] = File(...),
):
    try:
        record = await OffboardingService.submit_documents(
            db, record_id, user, files=files, note=note
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(data=_record_to_out(db, record), message="交接文档已提交")


@router.post("/{record_id}/confirm-handover", response_model=ResponseBase[OffboardingRecordOut])
def confirm_handover(
    db: DbSession,
    user: CurrentUser,
    record_id: int,
    data: OffboardingConfirmHandoverRequest,
):
    try:
        record = OffboardingService.confirm_handover(db, record_id, user, note=data.note)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(data=_record_to_out(db, record), message="交接已确认，等待超管最终批准")


@router.post("/{record_id}/approve", response_model=ResponseBase[OffboardingRecordOut])
def approve_offboarding(db: DbSession, operator: SuperAdminUser, record_id: int):
    try:
        record = OffboardingService.approve(db, record_id, operator)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(data=_record_to_out(db, record), message="离职交接已完成")


@router.post("/{record_id}/complete", response_model=ResponseBase[OffboardingRecordOut])
def complete_offboarding_legacy(
    db: DbSession,
    operator: SuperAdminUser,
    record_id: int,
    data: OffboardingAssignHandoverRequest,
):
    """兼容旧前端：等同于 assign-handover"""
    try:
        record = OffboardingService.assign_handover(
            db,
            record_id,
            operator,
            handover_user_id=data.handover_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseBase(data=_record_to_out(db, record), message="已指定交接人")


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
