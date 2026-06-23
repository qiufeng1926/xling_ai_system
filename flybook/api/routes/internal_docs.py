"""内部 API：导出文档正文供 xlink 同步快照"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from api.feishu_errors import feishu_error_to_http
from integrations.feishu.docx_export import export_document_text
from integrations.feishu.errors import FeishuError
from integrations.feishu.file_types import build_file_url
from services.feishu_session import ensure_user_access_token
from services.portal_tokens import PortalTokenError
from config.config import flybook_internal_key

router = APIRouter(prefix="/internal/documents", tags=["内部-云文档"])


def _verify_internal_key(x_flybook_internal_key: str = Header(default="")) -> None:
    expected = (flybook_internal_key or "").strip()
    if not expected or x_flybook_internal_key != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无效的内部密钥")


@router.get("/{token}/export-text", dependencies=[Depends(_verify_internal_key)])
def export_text(
    token: str,
    user_id: int = Query(..., ge=1),
    file_type: str = Query("docx", max_length=32),
):
    try:
        access_token, _ = ensure_user_access_token(user_id=user_id)
        exported = export_document_text(access_token, token=token, file_type=file_type)
    except PortalTokenError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FeishuError as exc:
        raise feishu_error_to_http(exc) from exc

    normalized = (file_type or "docx").strip().lower()
    return {
        "token": token,
        "file_type": normalized,
        "title": exported.get("title") or "",
        "content": exported.get("content") or "",
        "url": exported.get("url") or build_file_url(normalized, token),
    }
