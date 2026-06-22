from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AdminUser, CurrentUser
from app.schemas import ResponseBase
from app.schemas.qywechat_approval import (
    WeComApprovalApplyOut,
    WeComApprovalApplyRequest,
    WeComApprovalConfigOut,
    WeComApprovalDetailOut,
    WeComApprovalListOut,
    WeComApprovalTemplateOut,
    WeComApprovalTemplateRequest,
)
from app.services.qywechat_approval_service import WeComApprovalService

router = APIRouter(tags=["企业微信审批"])


@router.get("/config", response_model=ResponseBase[WeComApprovalConfigOut])
def get_qywechat_approval_config(_: CurrentUser):
    return ResponseBase(data=WeComApprovalConfigOut(**WeComApprovalService.get_config()))


@router.post("/templates/detail", response_model=ResponseBase[WeComApprovalTemplateOut])
def get_qywechat_approval_template(body: WeComApprovalTemplateRequest, _: AdminUser):
    try:
        data = WeComApprovalService.get_template_detail(body.template_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=WeComApprovalService.translate_error(exc),
        ) from exc
    return ResponseBase(data=WeComApprovalTemplateOut(**data))


@router.get("/list", response_model=ResponseBase[WeComApprovalListOut])
def list_qywechat_approvals(
    _: AdminUser,
    days: int = Query(7, ge=1, le=31),
    sp_status: str | None = Query(None),
    template_id: str | None = Query(None),
    creator: str | None = Query(None),
    cursor: str | None = Query(None),
    size: int = Query(50, ge=1, le=100),
):
    try:
        data = WeComApprovalService.list_approvals(
            days=days,
            sp_status=sp_status,
            template_id=template_id,
            creator=creator,
            cursor=cursor,
            size=size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=WeComApprovalService.translate_error(exc),
        ) from exc
    return ResponseBase(data=WeComApprovalListOut(**data))


@router.get("/detail/{sp_no}", response_model=ResponseBase[WeComApprovalDetailOut])
def get_qywechat_approval_detail(sp_no: str, _: AdminUser):
    try:
        data = WeComApprovalService.get_approval_detail(sp_no)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=WeComApprovalService.translate_error(exc),
        ) from exc
    return ResponseBase(data=WeComApprovalDetailOut(**data))


@router.post("/submit", response_model=ResponseBase[WeComApprovalApplyOut])
def submit_qywechat_approval(body: WeComApprovalApplyRequest, _: AdminUser):
    try:
        data = WeComApprovalService.submit_approval(
            template_id=body.template_id,
            creator_userid=body.creator_userid,
            use_template_approver=body.use_template_approver,
            choose_department=body.choose_department,
            contents=[item.model_dump() for item in body.contents],
            summary_lines=body.summary_lines,
            process=body.process,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=WeComApprovalService.translate_error(exc),
        ) from exc
    return ResponseBase(data=WeComApprovalApplyOut(**data), message="审批已提交")
