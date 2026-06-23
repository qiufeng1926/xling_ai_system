"""flybook 内部：注册云文档镜像"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import DbSession
from app.config import settings
from app.schemas import ResponseBase
from app.services.feishu_document_service import FeishuDocumentService

router = APIRouter(prefix="/internal/feishu-documents", tags=["内部-飞书文档镜像"])


class InternalRegisterBody(BaseModel):
    user_id: int = Field(..., ge=1)
    feishu_token: str = Field(..., min_length=8, max_length=128)
    feishu_type: str = Field(default="docx", max_length=32)
    title: str = Field(default="", max_length=500)
    feishu_url: str = Field(default="", max_length=2048)
    content: str = Field(default="")


def _verify_internal_key(x_flybook_internal_key: str = Header(default="")) -> None:
    expected = (settings.FLYBOOK_INTERNAL_KEY or "").strip()
    if not expected or x_flybook_internal_key != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无效的内部密钥")


@router.post("/register", response_model=ResponseBase[dict], dependencies=[Depends(_verify_internal_key)])
def internal_register_mirror(body: InternalRegisterBody, db: DbSession):
    mirror = FeishuDocumentService.register_or_update(
        db,
        user_id=body.user_id,
        feishu_token=body.feishu_token,
        feishu_type=body.feishu_type,
        title=body.title,
        feishu_url=body.feishu_url,
        content=body.content,
    )
    return ResponseBase(
        data={
            "doc_id": mirror.doc_id,
            "feishu_token": mirror.feishu_token,
            "synced_at": mirror.synced_at.isoformat() if mirror.synced_at else None,
        }
    )
