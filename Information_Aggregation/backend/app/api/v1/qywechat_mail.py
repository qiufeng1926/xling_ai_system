from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AdminUser, CurrentUser
from app.schemas import ResponseBase
from app.schemas.qywechat_mail import (
    WeComMailConfigOut,
    WeComMailDetailOut,
    WeComMailListOut,
    WeComMailSendRequest,
)
from app.services.qywechat_mail_service import WeComMailService

router = APIRouter(tags=["企业微信邮箱"])


@router.get("/config", response_model=ResponseBase[WeComMailConfigOut])
def get_qywechat_mail_config(_: CurrentUser):
    return ResponseBase(data=WeComMailConfigOut(**WeComMailService.get_config()))


@router.get("/inbox", response_model=ResponseBase[WeComMailListOut])
def list_qywechat_inbox(
    _: AdminUser,
    begin_time: int | None = Query(None),
    end_time: int | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=1000),
    days: int = Query(7, ge=1, le=31),
):
    try:
        data = WeComMailService.list_inbox(
            begin_time=begin_time,
            end_time=end_time,
            cursor=cursor,
            limit=limit,
            days=days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=WeComMailService.translate_error(exc),
        ) from exc
    return ResponseBase(data=WeComMailListOut(**data))


@router.get("/{mail_id}", response_model=ResponseBase[WeComMailDetailOut])
def get_qywechat_mail_detail(mail_id: str, _: AdminUser):
    try:
        data = WeComMailService.get_mail_detail(mail_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=WeComMailService.translate_error(exc),
        ) from exc
    return ResponseBase(data=WeComMailDetailOut(**data))


@router.post("/send", response_model=ResponseBase[None])
def send_qywechat_mail(body: WeComMailSendRequest, _: AdminUser):
    try:
        WeComMailService.send_mail(
            to_emails=body.to_emails,
            to_userids=body.to_userids,
            cc_emails=body.cc_emails,
            cc_userids=body.cc_userids,
            bcc_emails=body.bcc_emails,
            bcc_userids=body.bcc_userids,
            subject=body.subject,
            content=body.content,
            content_type=body.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=WeComMailService.translate_error(exc),
        ) from exc
    return ResponseBase(message="邮件已发送")
