from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth_utils import get_current_user, get_super_admin, require_user_id
from api.portal_auth import PortalUser
from config.config import agent_max_upload_mb, workspace_root
from db.models import KnowledgeBase, KnowledgeDocument
from db.session import get_db
from rag.retrieve import ingest_document

router = APIRouter(prefix="/v1/knowledge-bases", tags=["knowledge"])

ALLOWED_EXT = {".pdf", ".docx", ".md", ".txt", ".xlsx", ".xls", ".html", ".htm"}


class KBCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = "private"  # private | global


def _kb_dict(kb: KnowledgeBase) -> dict:
    return {
        "id": kb.id,
        "name": kb.name,
        "kind": kb.kind,
        "owner_user_id": kb.owner_user_id,
        "created_at": kb.created_at.isoformat() if kb.created_at else None,
    }


@router.get("")
def list_kbs(
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    private = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.kind == "private", KnowledgeBase.owner_user_id == uid)
        .all()
    )
    global_kbs = db.query(KnowledgeBase).filter(KnowledgeBase.kind == "global").all()
    return {"private": [_kb_dict(k) for k in private], "global": [_kb_dict(k) for k in global_kbs]}


@router.post("")
def create_kb(
    body: KBCreate,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    if body.kind == "global":
        if not user.is_super_admin:
            raise HTTPException(403, "仅超管可创建全局知识库")
        row = KnowledgeBase(owner_user_id=None, kind="global", name=body.name)
    else:
        row = KnowledgeBase(owner_user_id=uid, kind="private", name=body.name)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _kb_dict(row)


def _assert_kb_access(kb: KnowledgeBase, user: PortalUser, *, write: bool) -> None:
    uid = require_user_id(user)
    if kb.kind == "global":
        if write and not user.is_super_admin:
            raise HTTPException(403, "仅超管可管理全局库")
        return
    if kb.owner_user_id != uid:
        raise HTTPException(404, "知识库不存在")


@router.get("/{kb_id}/documents")
def list_docs(
    kb_id: int,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")
    _assert_kb_access(kb, user, write=False)
    docs = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.kb_id == kb_id)
        .order_by(KnowledgeDocument.id.desc())
        .all()
    )
    return {
        "items": [
            {
                "id": d.id,
                "filename": d.filename,
                "mime": d.mime,
                "size": d.size,
                "status": d.status,
                "error_message": d.error_message,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ]
    }


@router.post("/{kb_id}/documents")
async def upload_doc(
    kb_id: int,
    file: UploadFile = File(...),
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")
    _assert_kb_access(kb, user, write=True)
    uid = require_user_id(user)

    filename = Path(file.filename or "upload.bin").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXT:
        raise HTTPException(400, f"不支持的文件类型: {suffix}")

    data = await file.read()
    max_bytes = agent_max_upload_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(400, f"单文件上限 {agent_max_upload_mb}MB")

    store_dir = workspace_root / "kb" / str(kb_id)
    store_dir.mkdir(parents=True, exist_ok=True)
    store_path = store_dir / f"{uuid.uuid4().hex}{suffix}"
    store_path.write_bytes(data)

    doc = KnowledgeDocument(
        kb_id=kb_id,
        user_id=uid,
        filename=filename,
        mime=file.content_type or "application/octet-stream",
        size=len(data),
        status="pending",
        storage_path=str(store_path),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    await ingest_document(db, doc, kb.kind, kb.owner_user_id)
    db.refresh(doc)
    return {
        "id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "error_message": doc.error_message,
    }


@router.delete("/{kb_id}/documents/{doc_id}")
def delete_doc(
    kb_id: int,
    doc_id: int,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")
    _assert_kb_access(kb, user, write=True)
    doc = db.get(KnowledgeDocument, doc_id)
    if not doc or doc.kb_id != kb_id:
        raise HTTPException(404, "文档不存在")
    path = Path(doc.storage_path)
    if path.exists():
        path.unlink(missing_ok=True)
    db.delete(doc)
    db.commit()
    return {"ok": True}


# 超管快捷：确保存在默认全局库
@router.post("/ensure-global")
def ensure_global(
    user: PortalUser = Depends(get_super_admin),
    db: Session = Depends(get_db),
):
    row = db.query(KnowledgeBase).filter(KnowledgeBase.kind == "global").first()
    if not row:
        row = KnowledgeBase(kind="global", name="全局知识库", owner_user_id=None)
        db.add(row)
        db.commit()
        db.refresh(row)
    return _kb_dict(row)
