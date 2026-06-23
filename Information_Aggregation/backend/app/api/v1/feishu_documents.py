"""飞书云文档镜像 API"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession
from app.schemas import ResponseBase
from app.services.feishu_document_service import FeishuDocumentService

router = APIRouter(prefix="/feishu-documents", tags=["飞书云文档镜像"])


class DocumentAccessApplyBody(BaseModel):
    doc_ids: list[str] = Field(..., min_length=1, max_length=50)
    reason: str = Field(default="", max_length=500)


class DocumentAccessReviewBody(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    review_note: str = Field(default="", max_length=500)


@router.get("/list", response_model=ResponseBase[dict])
def list_document_mirrors(
    db: DbSession,
    user: CurrentUser,
    query: str = Query("", max_length=100),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    items, total = FeishuDocumentService.list_for_viewer(db, user, limit=limit, offset=offset, query=query)
    return ResponseBase(data={"items": items, "total": total})


@router.post("/access-requests", response_model=ResponseBase[dict])
def apply_document_view_access(body: DocumentAccessApplyBody, db: DbSession, user: CurrentUser):
    result = FeishuDocumentService.apply_view_access(db, user, body.doc_ids, body.reason)
    return ResponseBase(data=result)


@router.post("/download-requests", response_model=ResponseBase[dict])
def apply_document_download_access(body: DocumentAccessApplyBody, db: DbSession, user: CurrentUser):
    result = FeishuDocumentService.apply_download_access(db, user, body.doc_ids, body.reason)
    return ResponseBase(data=result)


@router.get("/access-requests/stats", response_model=ResponseBase[dict])
def document_access_stats(db: DbSession, user: CurrentUser):
    return ResponseBase(data=FeishuDocumentService.access_request_stats(db, user))


@router.get("/access-requests/pending", response_model=ResponseBase[dict])
def pending_document_view_requests(db: DbSession, user: CurrentUser):
    from app.utils.document_permissions import can_approve_document_view

    if not can_approve_document_view(user):
        raise HTTPException(status_code=403, detail="无权查看待审批列表")
    rows = FeishuDocumentService.list_pending_view_requests(db, user)
    return ResponseBase(
        data={
            "requests": [
                {
                    "id": r.id,
                    "doc_id": r.doc_id,
                    "document_title": r.document_title,
                    "username": r.applicant_username,
                    "nickname": r.applicant_nickname,
                    "reason": r.reason,
                    "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
        }
    )


@router.get("/download-requests/pending", response_model=ResponseBase[dict])
def pending_document_download_requests(db: DbSession, user: CurrentUser):
    from app.utils.document_permissions import can_approve_document_download

    if not can_approve_document_download(user):
        raise HTTPException(status_code=403, detail="无权查看待审批列表")
    rows = FeishuDocumentService.list_pending_download_requests(db, user)
    return ResponseBase(
        data={
            "requests": [
                {
                    "id": r.id,
                    "doc_id": r.doc_id,
                    "document_title": r.document_title,
                    "username": r.applicant_username,
                    "nickname": r.applicant_nickname,
                    "reason": r.reason,
                    "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
        }
    )


@router.post("/access-requests/{request_id}/review", response_model=ResponseBase[dict])
def review_document_view_request(
    request_id: int, body: DocumentAccessReviewBody, db: DbSession, user: CurrentUser
):
    try:
        FeishuDocumentService.review_view_request(
            db, user, request_id, approve=body.action == "approve", note=body.review_note
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseBase(data={"success": True})


@router.post("/download-requests/{request_id}/review", response_model=ResponseBase[dict])
def review_document_download_request(
    request_id: int, body: DocumentAccessReviewBody, db: DbSession, user: CurrentUser
):
    try:
        FeishuDocumentService.review_download_request(
            db, user, request_id, approve=body.action == "approve", note=body.review_note
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseBase(data={"success": True})


@router.get("/{doc_id}", response_model=ResponseBase[dict])
def get_document_mirror(doc_id: str, db: DbSession, user: CurrentUser):
    try:
        data = FeishuDocumentService.get_detail(db, user, doc_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ResponseBase(data=data)


@router.post("/{doc_id}/sync", response_model=ResponseBase[dict])
def sync_document_mirror(doc_id: str, db: DbSession, user: CurrentUser):
    from app.models.feishu_document import FeishuDocumentMirror

    mirror = db.query(FeishuDocumentMirror).filter(FeishuDocumentMirror.doc_id == doc_id).first()
    if not mirror:
        raise HTTPException(status_code=404, detail="文档不存在")
    if mirror.user_id != user.id:
        raise HTTPException(status_code=403, detail="仅文档所有者可触发同步")
    try:
        mirror = FeishuDocumentService.sync_from_flybook(db, mirror)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseBase(
        data={
            "doc_id": mirror.doc_id,
            "synced_at": mirror.synced_at.isoformat() if mirror.synced_at else None,
        }
    )
