"""飞书云文档 API（列表、多类型创建、组件鉴权）"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from api.auth_utils import get_current_user
from api.feishu_errors import feishu_error_to_http
from api.portal_auth import PortalUser
from integrations.feishu.docs import (
    CREATE_TYPES,
    create_cloud_file,
    enrich_file_item,
    get_root_folder_meta,
    list_files,
)
from integrations.feishu.errors import FeishuError
from integrations.feishu.file_types import CREATE_TYPE_LABELS, CREATE_TYPE_ORDER, LISTABLE_TYPES
from integrations.feishu.import_docs import get_import_formats, import_local_file, suggest_import_target
from integrations.feishu.docx_export import export_document_text
from services.feishu_session import ensure_user_access_token
from services.jssdk_auth import build_component_auth
from services.portal_documents import register_document_mirror
from services.portal_tokens import PortalTokenError
from utils.logger import get_logger

router = APIRouter(prefix="/docs", tags=["飞书云文档"])
logger = get_logger("docs")


class ComponentAuthRequest(BaseModel):
    page_url: str = Field(..., min_length=8, max_length=2048)


class CreateDocRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    type: str = Field(default="docx", max_length=32)
    folder_token: str = Field(default="", max_length=128)


def _require_user_id(user: PortalUser) -> int:
    if user.user_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无法识别当前用户")
    return int(user.user_id)


def _mirror_created_document(user_id: int, created: dict) -> None:
    """创建/导入成功后注册 xlink 文档镜像（失败不影响主流程）"""
    token = (created.get("token") or "").strip()
    if not token:
        return
    file_type = (created.get("type") or "docx").strip().lower()
    title = (created.get("title") or "").strip()
    url = (created.get("url") or "").strip()
    content = ""
    if file_type in {"docx", "doc"}:
        try:
            access_token, _ = ensure_user_access_token(user_id=user_id)
            exported = export_document_text(access_token, token=token, file_type=file_type)
            title = (exported.get("title") or title).strip()
            url = (exported.get("url") or url).strip()
            content = (exported.get("content") or "").strip()
        except Exception as exc:
            logger.warning(
                "导出文档正文用于镜像失败",
                extra={"output_params": {"user_id": user_id, "token": token, "error": str(exc)[:200]}},
            )
    register_document_mirror(
        user_id=user_id,
        feishu_token=token,
        feishu_type=file_type,
        title=title,
        feishu_url=url,
        content=content,
    )


@router.get("/create-types")
def docs_create_types(_user: PortalUser = Depends(get_current_user)):
    """前端「新建」菜单可选类型"""
    return {
        "types": [
            {
                "type": t,
                "label": CREATE_TYPE_LABELS.get(t, t),
                "embed_editable": t in {"docx"},
            }
            for t in CREATE_TYPE_ORDER
        ]
    }


@router.post("/component-auth")
def docs_component_auth(body: ComponentAuthRequest, user: PortalUser = Depends(get_current_user)):
    """云文档组件 DocComponentSdk 鉴权参数"""
    user_id = _require_user_id(user)
    try:
        access_token, open_id = ensure_user_access_token(user_id=user_id)
        auth = build_component_auth(
            user_access_token=access_token,
            open_id=open_id,
            page_url=body.page_url,
        )
    except PortalTokenError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FeishuError as exc:
        raise feishu_error_to_http(exc) from exc
    return auth


@router.get("/root-folder")
def docs_root_folder(user: PortalUser = Depends(get_current_user)):
    user_id = _require_user_id(user)
    try:
        access_token, _ = ensure_user_access_token(user_id=user_id)
        meta = get_root_folder_meta(access_token)
    except PortalTokenError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FeishuError as exc:
        raise feishu_error_to_http(exc) from exc
    return meta


@router.get("/files")
def docs_list_files(
    user: PortalUser = Depends(get_current_user),
    folder_token: str = Query("", max_length=128),
    page_size: int = Query(50, ge=1, le=100),
    page_token: str = Query("", max_length=256),
):
    user_id = _require_user_id(user)
    try:
        access_token, _ = ensure_user_access_token(user_id=user_id)
        data = list_files(
            access_token,
            folder_token=folder_token,
            page_size=page_size,
            page_token=page_token,
        )
    except PortalTokenError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FeishuError as exc:
        raise feishu_error_to_http(exc) from exc

    files = []
    for item in data.get("files") or []:
        if not isinstance(item, dict):
            continue
        file_type = (item.get("type") or "").strip()
        if file_type not in LISTABLE_TYPES:
            continue
        files.append(enrich_file_item(item))
    return {
        "files": files,
        "has_more": bool(data.get("has_more")),
        "page_token": data.get("page_token") or "",
    }


@router.post("/files")
def docs_create_file(body: CreateDocRequest, user: PortalUser = Depends(get_current_user)):
    user_id = _require_user_id(user)
    file_type = (body.type or "docx").strip().lower()
    if file_type not in CREATE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的类型: {body.type}，可选: {', '.join(sorted(CREATE_TYPES))}",
        )
    try:
        access_token, _ = ensure_user_access_token(user_id=user_id)
        created = create_cloud_file(
            access_token,
            file_type=file_type,
            title=body.title.strip(),
            folder_token=body.folder_token.strip(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PortalTokenError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FeishuError as exc:
        raise feishu_error_to_http(exc) from exc

    logger.info(
        "创建飞书云文件",
        extra={
            "output_params": {
                "user_id": user_id,
                "type": file_type,
                "token": created.get("token"),
            }
        },
    )
    _mirror_created_document(user_id, created)
    return created


@router.get("/import/formats")
def docs_import_formats(_user: PortalUser = Depends(get_current_user)):
    """本地文件导入：支持格式与大小限制"""
    return get_import_formats()


@router.get("/import/suggest")
def docs_import_suggest(
    filename: str = Query(..., min_length=1, max_length=256),
    _user: PortalUser = Depends(get_current_user),
):
    """根据文件名推荐导入目标类型"""
    return suggest_import_target(filename)


@router.post("/import")
async def docs_import_file(
    user: PortalUser = Depends(get_current_user),
    file: UploadFile = File(...),
    target_type: str = Form(..., max_length=32),
    folder_token: str = Form("", max_length=128),
    display_name: str = Form("", max_length=200),
):
    """上传本地文件并导入为飞书云文档（同步轮询至完成）"""
    user_id = _require_user_id(user)
    raw_name = (file.filename or "upload.bin").strip()
    content = await file.read()
    try:
        access_token, _ = ensure_user_access_token(user_id=user_id)
        created = import_local_file(
            access_token,
            filename=raw_name,
            content=content,
            target_type=target_type.strip().lower(),
            folder_token=folder_token.strip(),
            display_name=display_name.strip(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PortalTokenError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FeishuError as exc:
        raise feishu_error_to_http(exc) from exc

    logger.info(
        "导入飞书云文件",
        extra={
            "output_params": {
                "user_id": user_id,
                "type": created.get("type"),
                "token": created.get("token"),
                "source": raw_name,
            }
        },
    )
    _mirror_created_document(user_id, created)
    return created
