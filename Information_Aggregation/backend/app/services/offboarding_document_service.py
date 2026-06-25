"""离职交接文档存储"""

from __future__ import annotations

import mimetypes
import re
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR
from app.models.offboarding import UserOffboardingDocument, UserOffboardingRecord

UPLOAD_ROOT = BACKEND_DIR / "uploads" / "offboarding"
MAX_FILE_SIZE = 20 * 1024 * 1024
MAX_FILES_PER_SUBMIT = 10
ALLOWED_EXTENSIONS = frozenset(
    {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md", ".zip", ".png", ".jpg", ".jpeg"}
)


def _safe_filename(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^\w.\-()\u4e00-\u9fff]", "_", base)
    return base[:200] or "document"


class OffboardingDocumentService:
    @staticmethod
    def _record_dir(record_id: int) -> Path:
        path = UPLOAD_ROOT / str(record_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def list_documents(db: Session, record_id: int) -> list[dict]:
        rows = (
            db.query(UserOffboardingDocument)
            .filter(UserOffboardingDocument.record_id == record_id)
            .order_by(UserOffboardingDocument.uploaded_at.asc())
            .all()
        )
        return [
            {
                "id": row.id,
                "filename": row.filename,
                "file_size": row.file_size,
                "uploaded_at": row.uploaded_at,
            }
            for row in rows
        ]

    @staticmethod
    def get_document(db: Session, doc_id: int) -> UserOffboardingDocument | None:
        return db.query(UserOffboardingDocument).filter(UserOffboardingDocument.id == doc_id).first()

    @staticmethod
    def resolve_file_path(doc: UserOffboardingDocument) -> Path:
        return UPLOAD_ROOT / str(doc.record_id) / doc.stored_name

    @staticmethod
    async def save_uploads(
        db: Session,
        record: UserOffboardingRecord,
        files: list[UploadFile],
    ) -> list[UserOffboardingDocument]:
        if not files:
            raise ValueError("请至少上传一个交接文档")
        if len(files) > MAX_FILES_PER_SUBMIT:
            raise ValueError(f"单次最多上传 {MAX_FILES_PER_SUBMIT} 个文件")

        saved: list[UserOffboardingDocument] = []
        dest_dir = OffboardingDocumentService._record_dir(record.id)
        for upload in files:
            filename = _safe_filename(upload.filename or "document")
            ext = Path(filename).suffix.lower()
            if ext not in ALLOWED_EXTENSIONS:
                raise ValueError(f"不支持的文件类型: {ext or filename}")

            content = await upload.read()
            if len(content) > MAX_FILE_SIZE:
                raise ValueError(f"文件 {filename} 超过 20MB 限制")
            if not content:
                raise ValueError(f"文件 {filename} 为空")

            stored_name = f"{uuid.uuid4().hex}_{filename}"
            (dest_dir / stored_name).write_bytes(content)

            doc = UserOffboardingDocument(
                record_id=record.id,
                filename=filename,
                stored_name=stored_name,
                file_size=len(content),
            )
            db.add(doc)
            saved.append(doc)

        db.flush()
        return saved

    @staticmethod
    def guess_media_type(filename: str) -> str:
        mime, _ = mimetypes.guess_type(filename)
        return mime or "application/octet-stream"

    @staticmethod
    def delete_record_files(record_id: int) -> None:
        path = UPLOAD_ROOT / str(record_id)
        if not path.exists():
            return
        for item in path.iterdir():
            if item.is_file():
                item.unlink(missing_ok=True)
