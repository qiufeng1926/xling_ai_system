"""员工离职交接业务"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.constants.account_status import (
    ACTIVE,
    ACTIVE_RECORD_STATUSES,
    FINAL_APPROVAL_RETRY_STATUSES,
    OFFBOARDED,
    OFFBOARDING,
    OFFBOARD_RETENTION_DAYS,
    RECORD_AWAITING_DOCUMENTS,
    RECORD_AWAITING_FINAL_APPROVAL,
    RECORD_AWAITING_HANDOVER_CONFIRM,
    RECORD_CANCELLED,
    RECORD_COMPLETED,
    RECORD_FAILED,
    RECORD_PENDING,
    RECORD_PROCESSING,
)
from app.constants.roles import SUPER_ADMIN
from app.models import User
from app.models.collection import CollectionTask
from app.models.feishu_document import (
    FeishuDocumentDownloadGrant,
    FeishuDocumentDownloadRequest,
    FeishuDocumentMirror,
    FeishuDocumentViewGrant,
    FeishuDocumentViewRequest,
)
from app.models.match import MatchRequest
from app.models.offboarding import UserOffboardingDocument, UserOffboardingRecord
from app.models.permission import ViewAccessRequest
from app.services.flybook_client import FlybookClientError, mirror_all_documents_for_user
from app.services.meeting_ai_client import MeetingAiClientError, offboard_user, revert_offboard
from app.services.notification_emit import (
    notify_offboarding_completed,
    notify_offboarding_documents_submitted,
    notify_offboarding_handover_assigned,
    notify_offboarding_handover_confirmed,
    notify_offboarding_pending,
)
from app.services.offboarding_document_service import OffboardingDocumentService
from app.utils.access_control import can_manage_users, is_hidden_super_user, normalize_role, should_hide_user_from


class OffboardingService:
    @staticmethod
    def _active_user(db: Session, user_id: int) -> User | None:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        if user.status != 1 or getattr(user, "account_status", ACTIVE) != ACTIVE:
            return None
        return user

    @staticmethod
    def _record_out(db: Session, record: UserOffboardingRecord) -> dict:
        user = db.query(User).filter(User.id == record.user_id).first()
        handover = (
            db.query(User).filter(User.id == record.handover_user_id).first()
            if record.handover_user_id
            else None
        )
        return {
            "id": record.id,
            "user_id": record.user_id,
            "operator_id": record.operator_id,
            "handover_user_id": record.handover_user_id,
            "status": record.status,
            "reason": record.reason,
            "last_work_day": record.last_work_day,
            "content_snapshot": record.content_snapshot,
            "error_message": record.error_message,
            "applicant_note": record.applicant_note,
            "handover_confirm_note": record.handover_confirm_note,
            "handover_assigned_at": record.handover_assigned_at,
            "documents_submitted_at": record.documents_submitted_at,
            "handover_confirmed_at": record.handover_confirmed_at,
            "documents": OffboardingDocumentService.list_documents(db, record.id),
            "created_at": record.created_at,
            "started_at": record.started_at,
            "completed_at": record.completed_at,
            "expires_at": record.expires_at,
            "user_username": user.username if user else None,
            "user_nickname": (user.nickname or user.username) if user else None,
            "handover_username": handover.username if handover else None,
            "handover_nickname": (handover.nickname or handover.username) if handover else None,
        }

    @staticmethod
    def get_my_active(db: Session, user: User) -> UserOffboardingRecord | None:
        return (
            db.query(UserOffboardingRecord)
            .filter(
                UserOffboardingRecord.user_id == user.id,
                UserOffboardingRecord.status.in_(ACTIVE_RECORD_STATUSES),
            )
            .order_by(UserOffboardingRecord.id.desc())
            .first()
        )

    @staticmethod
    def get_my_pending(db: Session, user: User) -> UserOffboardingRecord | None:
        return OffboardingService.get_my_active(db, user)

    @staticmethod
    def apply(db: Session, user: User, *, reason: str | None = None, last_work_day: date | None = None) -> UserOffboardingRecord:
        if normalize_role(user.role) == SUPER_ADMIN:
            raise ValueError("超级管理员不可申请离职交接")
        if is_hidden_super_user(user):
            raise ValueError("无法申请离职交接")
        if getattr(user, "account_status", ACTIVE) != ACTIVE:
            raise ValueError("当前账号状态不可申请离职")

        existing = OffboardingService.get_my_active(db, user)
        if existing:
            raise ValueError("已有进行中的离职申请")

        record = UserOffboardingRecord(
            user_id=user.id,
            operator_id=user.id,
            status=RECORD_PENDING,
            reason=(reason or "").strip() or None,
            last_work_day=last_work_day,
        )
        user.account_status = OFFBOARDING
        db.add(record)
        db.commit()
        db.refresh(record)
        notify_offboarding_pending(db, record)
        return record

    @staticmethod
    def list_records(
        db: Session,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
    ) -> tuple[list[dict], int]:
        q = db.query(UserOffboardingRecord).order_by(UserOffboardingRecord.id.desc())
        if status:
            q = q.filter(UserOffboardingRecord.status == status)
        total = q.count()
        rows = q.offset((page - 1) * page_size).limit(page_size).all()
        return [OffboardingService._record_out(db, r) for r in rows], total

    @staticmethod
    def get_record(db: Session, record_id: int) -> UserOffboardingRecord | None:
        return db.query(UserOffboardingRecord).filter(UserOffboardingRecord.id == record_id).first()

    @staticmethod
    def list_handover_tasks(db: Session, user: User) -> list[dict]:
        q = db.query(UserOffboardingRecord).filter(
            UserOffboardingRecord.status == RECORD_AWAITING_HANDOVER_CONFIRM,
        )
        if not can_manage_users(user):
            q = q.filter(UserOffboardingRecord.handover_user_id == user.id)
        rows = q.order_by(UserOffboardingRecord.documents_submitted_at.desc()).all()
        return [OffboardingService._record_out(db, r) for r in rows]

    @staticmethod
    def list_handover_archive(db: Session, user: User) -> list[dict]:
        """交接人/超管查档：已提交文档的交接记录（含已确认、已完成）"""
        archive_statuses = (
            RECORD_AWAITING_HANDOVER_CONFIRM,
            RECORD_AWAITING_FINAL_APPROVAL,
            RECORD_PROCESSING,
            RECORD_COMPLETED,
            RECORD_FAILED,
        )
        q = db.query(UserOffboardingRecord).filter(
            UserOffboardingRecord.status.in_(archive_statuses),
            UserOffboardingRecord.documents_submitted_at.isnot(None),
        )
        if not can_manage_users(user):
            q = q.filter(UserOffboardingRecord.handover_user_id == user.id)
        rows = q.order_by(UserOffboardingRecord.documents_submitted_at.desc()).all()
        return [OffboardingService._record_out(db, r) for r in rows if r.documents_submitted_at]

    @staticmethod
    def cancel(db: Session, record_id: int, operator: User) -> UserOffboardingRecord:
        record = OffboardingService.get_record(db, record_id)
        if not record or record.status not in ACTIVE_RECORD_STATUSES:
            raise ValueError("离职申请不存在或不可取消")

        user = db.query(User).filter(User.id == record.user_id).first()
        if not user:
            raise ValueError("用户不存在")

        if record.meeting_snapshot:
            try:
                revert_offboard(record.meeting_snapshot)
            except MeetingAiClientError:
                pass

        record.status = RECORD_CANCELLED
        record.error_message = None
        record.meeting_snapshot = None
        record.started_at = None
        db.query(UserOffboardingDocument).filter(UserOffboardingDocument.record_id == record.id).delete(
            synchronize_session=False
        )
        OffboardingDocumentService.delete_record_files(record.id)
        user.account_status = ACTIVE
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def assign_handover(
        db: Session,
        record_id: int,
        operator: User,
        *,
        handover_user_id: int,
    ) -> UserOffboardingRecord:
        if normalize_role(operator.role) != SUPER_ADMIN:
            raise ValueError("需要超级管理员权限")

        record = OffboardingService.get_record(db, record_id)
        if not record or record.status != RECORD_PENDING:
            raise ValueError("仅待处理的申请可指定交接人")

        user = db.query(User).filter(User.id == record.user_id).first()
        if not user:
            raise ValueError("离职用户不存在")

        handover = OffboardingService._active_user(db, handover_user_id)
        if not handover:
            raise ValueError("对接人员无效或不在职")
        if handover.id == user.id:
            raise ValueError("对接人员不能是离职员工本人")

        record.handover_user_id = handover.id
        record.operator_id = operator.id
        record.status = RECORD_AWAITING_DOCUMENTS
        record.handover_assigned_at = datetime.now()
        record.error_message = None
        db.commit()
        db.refresh(record)
        notify_offboarding_handover_assigned(db, record)
        return record

    @staticmethod
    async def submit_documents(
        db: Session,
        record_id: int,
        user: User,
        *,
        files,
        note: str | None = None,
    ) -> UserOffboardingRecord:
        record = OffboardingService.get_record(db, record_id)
        if not record or record.user_id != user.id:
            raise ValueError("交接记录不存在")
        if record.status != RECORD_AWAITING_DOCUMENTS:
            raise ValueError("当前阶段不可提交交接文档")

        await OffboardingDocumentService.save_uploads(db, record, files)
        record.applicant_note = (note or "").strip() or None
        record.documents_submitted_at = datetime.now()
        record.status = RECORD_AWAITING_HANDOVER_CONFIRM
        record.error_message = None
        db.commit()
        db.refresh(record)
        notify_offboarding_documents_submitted(db, record)
        return record

    @staticmethod
    def confirm_handover(
        db: Session,
        record_id: int,
        handover_user: User,
        *,
        note: str | None = None,
    ) -> UserOffboardingRecord:
        record = OffboardingService.get_record(db, record_id)
        if not record or record.handover_user_id != handover_user.id:
            raise ValueError("交接记录不存在")
        if record.status != RECORD_AWAITING_HANDOVER_CONFIRM:
            raise ValueError("当前阶段不可确认交接")

        doc_count = (
            db.query(UserOffboardingDocument)
            .filter(UserOffboardingDocument.record_id == record.id)
            .count()
        )
        if doc_count == 0:
            raise ValueError("申请人尚未上传交接文档")

        record.handover_confirm_note = (note or "").strip() or None
        record.handover_confirmed_at = datetime.now()
        record.status = RECORD_AWAITING_FINAL_APPROVAL
        record.error_message = None
        db.commit()
        db.refresh(record)
        notify_offboarding_handover_confirmed(db, record)
        return record

    @staticmethod
    def approve(db: Session, record_id: int, operator: User) -> UserOffboardingRecord:
        if normalize_role(operator.role) != SUPER_ADMIN:
            raise ValueError("需要超级管理员权限")

        record = OffboardingService.get_record(db, record_id)
        if not record or record.status not in FINAL_APPROVAL_RETRY_STATUSES:
            raise ValueError("仅待最终批准的申请可执行离职封存")

        user = db.query(User).filter(User.id == record.user_id).first()
        if not user:
            raise ValueError("离职用户不存在")
        if getattr(user, "account_status", ACTIVE) != OFFBOARDING:
            raise ValueError("用户不在离职申请状态")

        handover = db.query(User).filter(User.id == record.handover_user_id).first()
        if not handover:
            raise ValueError("未指定交接人")

        if record.status in (RECORD_PROCESSING, RECORD_FAILED):
            OffboardingService._recover_partial_meeting(db, record)

        record.operator_id = operator.id
        record.status = RECORD_PROCESSING
        record.error_message = None
        record.started_at = datetime.now()
        db.commit()

        meeting_snapshot: dict = {}
        try:
            feishu_stats = OffboardingService._mirror_feishu_documents(db, user)
            meeting_snapshot = offboard_user(
                departed_username=user.username,
                handover_username=handover.username,
                offboarding_id=record.id,
            )
            record.meeting_snapshot = meeting_snapshot
            db.commit()

            snapshot = OffboardingService._transfer_portal_content(db, user, handover, record)
            snapshot["feishu_mirror"] = feishu_stats
            record.content_snapshot = snapshot
            record.error_message = None
            db.commit()
            db.refresh(record)
            notify_offboarding_completed(db, record)
            return record
        except Exception as exc:
            db.rollback()
            record = OffboardingService.get_record(db, record_id)
            if record and meeting_snapshot:
                try:
                    revert_offboard(meeting_snapshot)
                except MeetingAiClientError:
                    pass
            if record:
                record.status = RECORD_AWAITING_FINAL_APPROVAL
                record.error_message = str(exc)[:500]
                record.meeting_snapshot = None
                record.started_at = None
                user = db.query(User).filter(User.id == record.user_id).first()
                if user:
                    user.account_status = OFFBOARDING
                    user.status = 1
                db.commit()
            raise ValueError(str(exc)) from exc

    @staticmethod
    def complete(
        db: Session,
        record_id: int,
        operator: User,
        *,
        handover_user_id: int,
    ) -> UserOffboardingRecord:
        """兼容旧接口：指定交接人（不再直接完成封存）"""
        return OffboardingService.assign_handover(
            db, record_id, operator, handover_user_id=handover_user_id
        )

    @staticmethod
    def _recover_partial_meeting(db: Session, record: UserOffboardingRecord) -> None:
        if not record.meeting_snapshot:
            return
        try:
            revert_offboard(record.meeting_snapshot)
        except MeetingAiClientError:
            pass
        record.meeting_snapshot = None
        db.flush()

    @staticmethod
    def _mirror_feishu_documents(db: Session, user: User) -> dict:
        stats = {"mirrored": 0, "synced_existing": 0, "skipped": False, "errors": []}
        if not user.feishu_open_id:
            stats["skipped"] = True
            return stats

        try:
            remote = mirror_all_documents_for_user(user.id)
            stats["mirrored"] = int(remote.get("mirrored") or 0)
            stats["errors"] = list(remote.get("errors") or [])
        except FlybookClientError as exc:
            raise ValueError(f"飞书文档镜像失败: {exc}") from exc

        from app.services.feishu_document_service import FeishuDocumentService

        mirrors = db.query(FeishuDocumentMirror).filter(FeishuDocumentMirror.user_id == user.id).all()
        for mirror in mirrors:
            try:
                FeishuDocumentService.sync_from_flybook(db, mirror)
                stats["synced_existing"] += 1
            except Exception as exc:
                stats["errors"].append(f"{mirror.feishu_token}: {str(exc)[:120]}")
        return stats

    @staticmethod
    def _transfer_portal_content(
        db: Session,
        user: User,
        handover: User,
        record: UserOffboardingRecord,
    ) -> dict:
        snapshot: dict = {
            "collection_tasks": 0,
            "collection_tasks_deferred": 0,
            "match_requests": 0,
            "match_requests_deferred": 0,
            "feishu_documents": 0,
            "access_requests_rejected": 0,
            "access_requests_reassigned": 0,
            "feishu_requests_rejected": 0,
            "feishu_requests_reassigned": 0,
        }

        running_statuses = ("pending", "running")
        for task in db.query(CollectionTask).filter(CollectionTask.user_id == user.id).all():
            if task.status in running_statuses:
                task.transfer_pending_user_id = handover.id
                snapshot["collection_tasks_deferred"] += 1
            else:
                task.user_id = handover.id
                snapshot["collection_tasks"] += 1

        for req in db.query(MatchRequest).filter(MatchRequest.user_id == user.id).all():
            if req.status == "running":
                req.transfer_pending_user_id = handover.id
                snapshot["match_requests_deferred"] += 1
            else:
                req.user_id = handover.id
                snapshot["match_requests"] += 1

        doc_count = (
            db.query(FeishuDocumentMirror)
            .filter(FeishuDocumentMirror.user_id == user.id)
            .update(
                {
                    FeishuDocumentMirror.user_id: handover.id,
                    FeishuDocumentMirror.status: "archived",
                },
                synchronize_session=False,
            )
        )
        snapshot["feishu_documents"] = doc_count

        for model in (FeishuDocumentViewGrant, FeishuDocumentDownloadGrant):
            db.query(model).filter(model.user_id == user.id).delete(synchronize_session=False)

        now = datetime.now()
        for req in db.query(ViewAccessRequest).filter(ViewAccessRequest.user_id == user.id).all():
            if req.status == "pending":
                req.status = "rejected"
                req.review_note = "员工离职，申请自动拒绝"
                req.reviewed_at = now
                snapshot["access_requests_rejected"] += 1
            if req.applicant_username is None:
                req.applicant_username = user.username
                req.applicant_nickname = user.nickname

        for req in db.query(ViewAccessRequest).filter(
            ViewAccessRequest.reviewer_id == user.id,
            ViewAccessRequest.status == "pending",
        ).all():
            req.reviewer_id = handover.id
            req.reviewer_username = handover.username
            req.reviewer_nickname = handover.nickname
            snapshot["access_requests_reassigned"] += 1

        for model in (FeishuDocumentViewRequest, FeishuDocumentDownloadRequest):
            for req in db.query(model).filter(model.user_id == user.id).all():
                if req.status == "pending":
                    req.status = "rejected"
                    req.review_note = "员工离职，申请自动拒绝"
                    req.reviewed_at = now
                    snapshot["feishu_requests_rejected"] += 1
                if req.applicant_username is None:
                    req.applicant_username = user.username
                    req.applicant_nickname = user.nickname

            for req in db.query(model).filter(model.reviewer_id == user.id, model.status == "pending").all():
                req.reviewer_id = handover.id
                req.reviewer_username = handover.username
                req.reviewer_nickname = handover.nickname
                snapshot["feishu_requests_reassigned"] += 1

        user.feishu_open_id = None
        user.feishu_union_id = None
        user.feishu_name = None
        user.feishu_access_token = None
        user.feishu_refresh_token = None
        user.feishu_token_expires_at = None
        user.feishu_oauth_scope = None

        user.status = 0
        user.account_status = OFFBOARDED
        user.offboarded_at = now
        record.status = RECORD_COMPLETED
        record.completed_at = now
        record.expires_at = now + timedelta(days=OFFBOARD_RETENTION_DAYS)
        record.content_snapshot = snapshot
        return snapshot

    @staticmethod
    def rehire(db: Session, user_id: int, operator: User) -> User:
        if normalize_role(operator.role) != SUPER_ADMIN:
            raise ValueError("需要超级管理员权限")

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("用户不存在")
        if getattr(user, "account_status", ACTIVE) != OFFBOARDED:
            raise ValueError("用户未处于离职封存状态")

        record = (
            db.query(UserOffboardingRecord)
            .filter(
                UserOffboardingRecord.user_id == user.id,
                UserOffboardingRecord.status == RECORD_COMPLETED,
            )
            .order_by(UserOffboardingRecord.id.desc())
            .first()
        )
        if record and record.expires_at and record.expires_at < datetime.now():
            raise ValueError("已超过复职期限，无法重新开通")

        user.status = 1
        user.account_status = ACTIVE
        user.offboarded_at = None
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def expire_offboarded_accounts(db: Session) -> int:
        now = datetime.now()
        records = (
            db.query(UserOffboardingRecord)
            .filter(
                UserOffboardingRecord.status == RECORD_COMPLETED,
                UserOffboardingRecord.expires_at.isnot(None),
                UserOffboardingRecord.expires_at < now,
            )
            .all()
        )
        deleted = 0
        for record in records:
            user = db.query(User).filter(User.id == record.user_id).first()
            if not user:
                continue
            if getattr(user, "account_status", ACTIVE) != OFFBOARDED:
                continue
            db.delete(user)
            deleted += 1
        if deleted:
            db.commit()
        return deleted
