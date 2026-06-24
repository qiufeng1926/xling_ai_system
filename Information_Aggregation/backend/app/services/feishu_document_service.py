"""飞书云文档镜像：注册、同步快照、列表与权限申请"""

from __future__ import annotations

from datetime import datetime

import httpx
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User
from app.models.feishu_document import (
    FeishuDocumentDownloadGrant,
    FeishuDocumentDownloadRequest,
    FeishuDocumentMirror,
    FeishuDocumentSnapshot,
    FeishuDocumentViewGrant,
    FeishuDocumentViewRequest,
    new_doc_id,
)
from app.utils.access_control import (
    apply_hidden_user_scope,
    hidden_super_user_ids,
    is_hidden_super_user,
    is_super_admin,
    normalize_role,
    should_hide_user_from,
)
from app.utils.document_permissions import (
    can_access_document,
    can_approve_document_download,
    can_approve_document_view,
    can_download_document,
    can_view_all_documents,
)
from app.utils.user_permissions import effective_permissions


class FeishuDocumentService:
    @staticmethod
    def register_or_update(
        db: Session,
        *,
        user_id: int,
        feishu_token: str,
        feishu_type: str,
        title: str,
        feishu_url: str = "",
        content: str = "",
        content_format: str = "plain_text",
    ) -> FeishuDocumentMirror:
        token = feishu_token.strip()
        mirror = (
            db.query(FeishuDocumentMirror)
            .filter(FeishuDocumentMirror.user_id == user_id, FeishuDocumentMirror.feishu_token == token)
            .first()
        )
        now = datetime.now()
        if mirror is None:
            mirror = FeishuDocumentMirror(
                doc_id=new_doc_id(),
                user_id=user_id,
                feishu_token=token,
                feishu_type=(feishu_type or "docx").strip().lower(),
                title=(title or "未命名文档").strip()[:500],
                feishu_url=feishu_url or None,
                synced_at=now if content else None,
            )
            db.add(mirror)
            db.flush()
        else:
            mirror.title = (title or mirror.title or "未命名文档").strip()[:500]
            if feishu_url:
                mirror.feishu_url = feishu_url
            mirror.feishu_type = (feishu_type or mirror.feishu_type).strip().lower()
            if content:
                mirror.synced_at = now

        if content:
            snap = FeishuDocumentSnapshot(
                mirror_id=mirror.id,
                content=content,
                content_format=content_format,
                content_length=len(content),
                synced_at=now,
            )
            db.add(snap)
        db.commit()
        db.refresh(mirror)
        return mirror

    @staticmethod
    def sync_from_flybook(db: Session, mirror: FeishuDocumentMirror) -> FeishuDocumentMirror:
        """调用 flybook 拉取飞书正文并写入快照"""
        owner = db.query(User).filter(User.id == mirror.user_id).first()
        if not owner or not owner.feishu_access_token:
            raise ValueError("文档所有者未绑定飞书或 token 缺失")

        base = (settings.FLYBOOK_API_URL or "http://127.0.0.1:8002").rstrip("/")
        key = (settings.FLYBOOK_INTERNAL_KEY or "").strip()
        if not key:
            raise ValueError("未配置 FLYBOOK_INTERNAL_KEY")

        url = f"{base}/api/flybook/internal/documents/{mirror.feishu_token}/export-text"
        with httpx.Client(timeout=60.0) as client:
            resp = client.get(
                url,
                params={"user_id": mirror.user_id, "file_type": mirror.feishu_type},
                headers={"X-Flybook-Internal-Key": key},
            )
        if resp.status_code != 200:
            detail = resp.text[:200]
            raise ValueError(f"flybook 导出失败: {detail}")
        body = resp.json()
        content = (body.get("content") or "").strip()
        title = (body.get("title") or mirror.title or "").strip()

        return FeishuDocumentService.register_or_update(
            db,
            user_id=mirror.user_id,
            feishu_token=mirror.feishu_token,
            feishu_type=mirror.feishu_type,
            title=title,
            feishu_url=mirror.feishu_url or body.get("url") or "",
            content=content,
        )

    @staticmethod
    def _pending_request_status(db: Session, model, doc_id: str, user: User) -> str | None:
        q = db.query(model).filter(model.doc_id == doc_id, model.status == "pending")
        if user.id:
            q = q.filter(model.user_id == user.id)
        row = q.order_by(desc(model.created_at)).first()
        return row.status if row else None

    @staticmethod
    def list_for_viewer(
        db: Session,
        viewer: User,
        *,
        limit: int = 50,
        offset: int = 0,
        query: str = "",
    ) -> tuple[list[dict], int]:
        q = db.query(FeishuDocumentMirror).filter(
            or_(
                FeishuDocumentMirror.status == "active",
                FeishuDocumentMirror.user_id == viewer.id,
            )
        )
        q = apply_hidden_user_scope(db, q, viewer, FeishuDocumentMirror.user_id)

        if query.strip():
            like = f"%{query.strip()}%"
            q = q.filter(or_(FeishuDocumentMirror.title.like(like), FeishuDocumentMirror.feishu_token.like(like)))

        total = q.count()
        rows = q.order_by(desc(FeishuDocumentMirror.updated_at)).offset(offset).limit(limit).all()

        items: list[dict] = []
        for mirror in rows:
            owner = db.query(User).filter(User.id == mirror.user_id).first()
            allowed = can_access_document(db, viewer, mirror, owner)
            can_dl = can_download_document(db, viewer, mirror, owner) if allowed else False
            latest = (
                db.query(FeishuDocumentSnapshot)
                .filter(FeishuDocumentSnapshot.mirror_id == mirror.id)
                .order_by(desc(FeishuDocumentSnapshot.synced_at))
                .first()
            )
            preview = (latest.content[:120] + "…") if latest and len(latest.content) > 120 else (latest.content if latest else "")
            items.append(
                {
                    "doc_id": mirror.doc_id,
                    "feishu_token": mirror.feishu_token,
                    "feishu_type": mirror.feishu_type,
                    "title": mirror.title,
                    "feishu_url": mirror.feishu_url,
                    "owner_id": mirror.user_id,
                    "owner_username": owner.username if owner else None,
                    "owner_nickname": (owner.nickname or owner.username) if owner else None,
                    "archived": mirror.status == "archived",
                    "synced_at": mirror.synced_at.isoformat() if mirror.synced_at else None,
                    "has_snapshot": latest is not None,
                    "preview": preview if allowed else "",
                    "can_access": allowed,
                    "can_download": can_dl,
                    "access_request_status": None
                    if allowed
                    else FeishuDocumentService._pending_request_status(
                        db, FeishuDocumentViewRequest, mirror.doc_id, viewer
                    ),
                    "download_request_status": None
                    if can_dl
                    else FeishuDocumentService._pending_request_status(
                        db, FeishuDocumentDownloadRequest, mirror.doc_id, viewer
                    ),
                }
            )
        return items, total

    @staticmethod
    def get_detail(db: Session, viewer: User, doc_id: str) -> dict:
        mirror = db.query(FeishuDocumentMirror).filter(FeishuDocumentMirror.doc_id == doc_id).first()
        if not mirror:
            raise ValueError("文档不存在")
        owner = db.query(User).filter(User.id == mirror.user_id).first()
        if not can_access_document(db, viewer, mirror, owner):
            raise PermissionError("无权查看该文档")

        latest = (
            db.query(FeishuDocumentSnapshot)
            .filter(FeishuDocumentSnapshot.mirror_id == mirror.id)
            .order_by(desc(FeishuDocumentSnapshot.synced_at))
            .first()
        )
        return {
            "doc_id": mirror.doc_id,
            "feishu_token": mirror.feishu_token,
            "feishu_type": mirror.feishu_type,
            "title": mirror.title,
            "feishu_url": mirror.feishu_url,
            "owner_id": mirror.user_id,
            "owner_username": owner.username if owner else None,
            "synced_at": mirror.synced_at.isoformat() if mirror.synced_at else None,
            "content": latest.content if latest else "",
            "content_format": latest.content_format if latest else "plain_text",
            "can_download": can_download_document(db, viewer, mirror, owner),
        }

    @staticmethod
    def apply_view_access(db: Session, viewer: User, doc_ids: list[str], reason: str = "") -> dict:
        created = []
        skipped = []
        for doc_id in doc_ids:
            mirror = db.query(FeishuDocumentMirror).filter(FeishuDocumentMirror.doc_id == doc_id).first()
            if not mirror:
                skipped.append({"doc_id": doc_id, "reason": "文档不存在"})
                continue
            owner = db.query(User).filter(User.id == mirror.user_id).first()
            if can_access_document(db, viewer, mirror, owner):
                skipped.append({"doc_id": doc_id, "reason": "已有浏览权限"})
                continue
            if can_view_all_documents(viewer):
                skipped.append({"doc_id": doc_id, "reason": "您已具备浏览他人文档权限"})
                continue
            pending = (
                db.query(FeishuDocumentViewRequest)
                .filter(
                    FeishuDocumentViewRequest.doc_id == doc_id,
                    FeishuDocumentViewRequest.user_id == viewer.id,
                    FeishuDocumentViewRequest.status == "pending",
                )
                .first()
            )
            if pending:
                skipped.append({"doc_id": doc_id, "reason": "已有待审批申请"})
                continue
            req = FeishuDocumentViewRequest(
                doc_id=doc_id,
                user_id=viewer.id,
                applicant_username=viewer.username,
                applicant_nickname=viewer.nickname or viewer.username,
                document_title=mirror.title,
                reason=(reason or "").strip()[:500] or None,
            )
            db.add(req)
            db.flush()
            created.append(req)
        db.commit()
        if created:
            from app.services.notification_emit import notify_feishu_doc_request_created

            notify_feishu_doc_request_created(db, viewer.id, "view", len(created))
        return {"created": len(created), "skipped": skipped}

    @staticmethod
    def apply_download_access(db: Session, viewer: User, doc_ids: list[str], reason: str = "") -> dict:
        created = []
        skipped = []
        for doc_id in doc_ids:
            mirror = db.query(FeishuDocumentMirror).filter(FeishuDocumentMirror.doc_id == doc_id).first()
            if not mirror:
                skipped.append({"doc_id": doc_id, "reason": "文档不存在"})
                continue
            owner = db.query(User).filter(User.id == mirror.user_id).first()
            if not can_access_document(db, viewer, mirror, owner):
                skipped.append({"doc_id": doc_id, "reason": "需先获得浏览权限"})
                continue
            if can_download_document(db, viewer, mirror, owner):
                skipped.append({"doc_id": doc_id, "reason": "已有下载权限"})
                continue
            pending = (
                db.query(FeishuDocumentDownloadRequest)
                .filter(
                    FeishuDocumentDownloadRequest.doc_id == doc_id,
                    FeishuDocumentDownloadRequest.user_id == viewer.id,
                    FeishuDocumentDownloadRequest.status == "pending",
                )
                .first()
            )
            if pending:
                skipped.append({"doc_id": doc_id, "reason": "已有待审批申请"})
                continue
            req = FeishuDocumentDownloadRequest(
                doc_id=doc_id,
                user_id=viewer.id,
                applicant_username=viewer.username,
                applicant_nickname=viewer.nickname or viewer.username,
                document_title=mirror.title,
                reason=(reason or "").strip()[:500] or None,
            )
            db.add(req)
            db.flush()
            created.append(req)
        db.commit()
        if created:
            from app.services.notification_emit import notify_feishu_doc_request_created

            notify_feishu_doc_request_created(db, viewer.id, "download", len(created))
        return {"created": len(created), "skipped": skipped}

    @staticmethod
    def _filter_hidden_requests(db: Session, viewer: User, query, user_id_column):
        if is_hidden_super_user(viewer):
            return query
        hidden_ids = hidden_super_user_ids(db)
        if hidden_ids:
            return query.filter(
                or_(
                    user_id_column.is_(None),
                    ~user_id_column.in_(hidden_ids),
                )
            )
        return query

    @staticmethod
    def list_pending_view_requests(db: Session, reviewer: User) -> list[FeishuDocumentViewRequest]:
        q = db.query(FeishuDocumentViewRequest).filter(FeishuDocumentViewRequest.status == "pending")
        q = FeishuDocumentService._filter_hidden_requests(
            db, reviewer, q, FeishuDocumentViewRequest.user_id
        )
        return q.order_by(desc(FeishuDocumentViewRequest.created_at)).limit(200).all()

    @staticmethod
    def list_pending_download_requests(db: Session, reviewer: User) -> list[FeishuDocumentDownloadRequest]:
        q = db.query(FeishuDocumentDownloadRequest).filter(
            FeishuDocumentDownloadRequest.status == "pending"
        )
        q = FeishuDocumentService._filter_hidden_requests(
            db, reviewer, q, FeishuDocumentDownloadRequest.user_id
        )
        return q.order_by(desc(FeishuDocumentDownloadRequest.created_at)).limit(200).all()

    @staticmethod
    def review_view_request(db: Session, reviewer: User, request_id: int, approve: bool, note: str = "") -> None:
        if not can_approve_document_view(reviewer):
            raise PermissionError("无权审批文档浏览申请")
        req = db.query(FeishuDocumentViewRequest).filter(FeishuDocumentViewRequest.id == request_id).first()
        if not req or req.status != "pending":
            raise ValueError("申请不存在或已处理")
        req.status = "approved" if approve else "rejected"
        req.reviewer_id = reviewer.id
        req.reviewer_username = reviewer.username
        req.reviewer_nickname = reviewer.nickname or reviewer.username
        req.review_note = (note or "").strip()[:500] or None
        req.reviewed_at = datetime.now()
        if approve:
            db.add(
                FeishuDocumentViewGrant(
                    doc_id=req.doc_id,
                    user_id=req.user_id,
                    username=req.applicant_username,
                )
            )
        db.commit()
        from app.services.notification_emit import notify_feishu_doc_request_reviewed

        notify_feishu_doc_request_reviewed(req.user_id, "view", req.status)

    @staticmethod
    def review_download_request(db: Session, reviewer: User, request_id: int, approve: bool, note: str = "") -> None:
        if not can_approve_document_download(reviewer):
            raise PermissionError("无权审批文档下载申请")
        req = db.query(FeishuDocumentDownloadRequest).filter(FeishuDocumentDownloadRequest.id == request_id).first()
        if not req or req.status != "pending":
            raise ValueError("申请不存在或已处理")
        req.status = "approved" if approve else "rejected"
        req.reviewer_id = reviewer.id
        req.reviewer_username = reviewer.username
        req.reviewer_nickname = reviewer.nickname or reviewer.username
        req.review_note = (note or "").strip()[:500] or None
        req.reviewed_at = datetime.now()
        if approve:
            db.add(
                FeishuDocumentDownloadGrant(
                    doc_id=req.doc_id,
                    user_id=req.user_id,
                    username=req.applicant_username,
                )
            )
        db.commit()
        from app.services.notification_emit import notify_feishu_doc_request_reviewed

        notify_feishu_doc_request_reviewed(req.user_id, "download", req.status)

    @staticmethod
    def access_request_stats(db: Session, viewer: User) -> dict:
        my_view = (
            db.query(FeishuDocumentViewRequest)
            .filter(FeishuDocumentViewRequest.user_id == viewer.id, FeishuDocumentViewRequest.status == "pending")
            .count()
        )
        my_dl = (
            db.query(FeishuDocumentDownloadRequest)
            .filter(
                FeishuDocumentDownloadRequest.user_id == viewer.id,
                FeishuDocumentDownloadRequest.status == "pending",
            )
            .count()
        )
        pending_review = 0
        if can_approve_document_view(viewer):
            pending_review += len(FeishuDocumentService.list_pending_view_requests(db, viewer))
        if can_approve_document_download(viewer):
            pending_review += len(FeishuDocumentService.list_pending_download_requests(db, viewer))
        return {
            "my_pending": my_view + my_dl,
            "pending_for_review": pending_review,
        }
