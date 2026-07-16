from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from api.auth_utils import decode_access_token, get_current_user, require_user_id
from api.portal_auth import PortalUser, resolve_user_from_payload
from config.config import workspace_root
from db.models import KnowledgeBase, KnowledgeDocument, WorkspaceFile
from db.session import get_db
from rag.retrieve import ingest_document
from tools.runtime import user_workspace

router = APIRouter(prefix="/v1/workspace", tags=["workspace"])
_security = HTTPBearer(auto_error=False)


def _user_from_bearer_or_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
    token: str | None = Query(None),
) -> PortalUser:
    raw = None
    if credentials and credentials.credentials:
        raw = credentials.credentials
    elif token:
        raw = token
    if not raw:
        raise HTTPException(401, "请先登录")
    payload = decode_access_token(raw)
    user = resolve_user_from_payload(payload, bearer_token=raw)
    if not user or user.user_id is None:
        raise HTTPException(401, "用户不存在")
    return user


@router.get("/files")
def list_files(
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    rows = (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.user_id == uid)
        .order_by(WorkspaceFile.id.desc())
        .limit(200)
        .all()
    )
    return {
        "items": [
            {
                "id": r.id,
                "name": r.name,
                "mime": r.mime,
                "size": r.size,
                "conversation_id": r.conversation_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


@router.get("/files/{file_id}/download")
def download_file(
    file_id: int,
    user: PortalUser = Depends(_user_from_bearer_or_token),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    row = db.get(WorkspaceFile, file_id)
    if not row or row.user_id != uid:
        raise HTTPException(404, "文件不存在")
    path = Path(row.path)
    if not path.exists():
        raise HTTPException(404, "文件已丢失")
    root = user_workspace(uid).resolve()
    resolved = path.resolve()
    if not str(resolved).startswith(str(root)):
        raise HTTPException(403, "非法路径")
    return FileResponse(path, filename=row.name, media_type=row.mime)


@router.post("/files/{file_id}/archive")
async def archive_file(
    file_id: int,
    kb_id: int = Query(...),
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    row = db.get(WorkspaceFile, file_id)
    if not row or row.user_id != uid:
        raise HTTPException(404, "文件不存在")
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")
    if kb.kind == "private" and kb.owner_user_id != uid:
        raise HTTPException(403, "无权写入该知识库")
    if kb.kind == "global" and not user.is_super_admin:
        raise HTTPException(403, "仅超管可写入全局库")

    src = Path(row.path)
    if not src.exists():
        raise HTTPException(404, "文件已丢失")

    store_dir = workspace_root / "kb" / str(kb_id)
    store_dir.mkdir(parents=True, exist_ok=True)
    dest = store_dir / f"{uuid.uuid4().hex}{src.suffix}"
    shutil.copy2(src, dest)

    doc = KnowledgeDocument(
        kb_id=kb_id,
        user_id=uid,
        filename=row.name,
        mime=row.mime,
        size=row.size,
        status="pending",
        storage_path=str(dest),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    await ingest_document(db, doc, kb.kind, kb.owner_user_id)
    return {"doc_id": doc.id, "status": doc.status}
