from datetime import datetime

from sqlalchemy.orm import Session, aliased

from app.constants.permissions import (
    REQ_DOWNLOAD_MEETINGS,
    REQ_PROMOTE_ADMIN,
    REQ_VIEW_ALL_MEETINGS,
    REQ_VIEW_LIBRARY,
    REQ_VIEW_ROOT_MEETINGS,
    REQUEST_TYPE_LABELS,
)
from app.constants.roles import ADMIN, SUPER_ADMIN, USER
from app.models import User
from app.models.permission import SystemSetting, ViewAccessRequest
from app.schemas.user import ViewAccessRequestCreate
from app.utils.access_control import (
    SETTING_BLOCK_UPPER_TASKS,
    can_review_access,
    get_system_setting,
    hidden_super_user_ids,
    is_hidden_super_user,
    is_super_admin,
    normalize_role,
    should_hide_user_from,
)
from app.utils.user_permissions import can_apply_request_type, effective_permissions


class PermissionService:
    @staticmethod
    def _apply_hidden_request_scope(db: Session, query, viewer: User):
        if is_hidden_super_user(viewer):
            return query
        hidden_ids = hidden_super_user_ids(db)
        if not hidden_ids:
            return query
        return query.filter(
            ~ViewAccessRequest.user_id.in_(hidden_ids),
            (ViewAccessRequest.reviewer_id.is_(None)) | (~ViewAccessRequest.reviewer_id.in_(hidden_ids)),
        )

    @staticmethod
    def _apply_reviewer_list_scope(query, viewer: User):
        """审核员可见的申请范围（不含 status 过滤）。"""
        if not can_review_access(viewer):
            return query.filter(ViewAccessRequest.id < 0)

        viewer_role = normalize_role(viewer.role)
        if viewer_role == ADMIN:
            types = [REQ_VIEW_LIBRARY, REQ_VIEW_ALL_MEETINGS]
            if bool(getattr(viewer, "approve_meeting_download", False)):
                types.append(REQ_DOWNLOAD_MEETINGS)
            return query.filter(ViewAccessRequest.request_type.in_(types))
        return query

    @staticmethod
    def get_access_request_stats(db: Session, viewer: User) -> dict:
        my_pending = (
            db.query(ViewAccessRequest)
            .filter(
                ViewAccessRequest.user_id == viewer.id,
                ViewAccessRequest.status == "pending",
            )
            .count()
        )
        my_total = (
            db.query(ViewAccessRequest)
            .filter(ViewAccessRequest.user_id == viewer.id)
            .count()
        )

        pending_for_review = 0
        if can_review_access(viewer):
            q = db.query(ViewAccessRequest).filter(ViewAccessRequest.status == "pending")
            q = PermissionService._apply_reviewer_list_scope(q, viewer)
            q = PermissionService._apply_hidden_request_scope(db, q, viewer)
            pending_for_review = q.count()

        return {
            "my_pending": my_pending,
            "my_total": my_total,
            "pending_for_review": pending_for_review,
            "can_review": can_review_access(viewer),
        }

    @staticmethod
    def create_access_request(db: Session, user: User, data: ViewAccessRequestCreate) -> ViewAccessRequest:
        ok, message = can_apply_request_type(user, data.request_type)
        if not ok:
            raise ValueError(message)

        pending = (
            db.query(ViewAccessRequest)
            .filter(
                ViewAccessRequest.user_id == user.id,
                ViewAccessRequest.request_type == data.request_type,
                ViewAccessRequest.status == "pending",
            )
            .first()
        )
        if pending:
            raise ValueError("已有待审核的同类申请，请等待管理员处理")

        req = ViewAccessRequest(
            user_id=user.id,
            request_type=data.request_type,
            reason=data.reason,
            status="pending",
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        return req

    @staticmethod
    def list_access_requests(
        db: Session,
        viewer: User,
        status: str | None = None,
        request_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
        scope: str | None = None,
    ) -> tuple[list[dict], int]:
        Applicant = aliased(User)
        Reviewer = aliased(User)

        query = (
            db.query(
                ViewAccessRequest,
                Applicant.username,
                Applicant.nickname,
                Reviewer.username,
                Reviewer.nickname,
            )
            .join(Applicant, ViewAccessRequest.user_id == Applicant.id)
            .outerjoin(Reviewer, ViewAccessRequest.reviewer_id == Reviewer.id)
        )

        if scope == "mine":
            query = query.filter(ViewAccessRequest.user_id == viewer.id)
        elif scope == "review":
            query = PermissionService._apply_reviewer_list_scope(query, viewer)
        elif can_review_access(viewer):
            query = PermissionService._apply_reviewer_list_scope(query, viewer)
        else:
            query = query.filter(ViewAccessRequest.user_id == viewer.id)

        query = PermissionService._apply_hidden_request_scope(db, query, viewer)

        if status:
            query = query.filter(ViewAccessRequest.status == status)
        if request_type:
            query = query.filter(ViewAccessRequest.request_type == request_type)

        query = query.order_by(ViewAccessRequest.created_at.desc())
        total = query.count()
        rows = query.offset((page - 1) * page_size).limit(page_size).all()

        result = []
        for item, username, nickname, reviewer_username, reviewer_nickname in rows:
            result.append(
                {
                    "id": item.id,
                    "user_id": item.user_id,
                    "request_type": item.request_type,
                    "status": item.status,
                    "reason": item.reason,
                    "reviewer_id": item.reviewer_id,
                    "review_note": item.review_note,
                    "created_at": item.created_at,
                    "reviewed_at": item.reviewed_at,
                    "username": username,
                    "nickname": nickname,
                    "reviewer_username": reviewer_username,
                    "reviewer_nickname": reviewer_nickname,
                    "request_type_label": REQUEST_TYPE_LABELS.get(item.request_type, item.request_type),
                }
            )
        return result, total

    @staticmethod
    def _can_reviewer_handle(viewer: User, req: ViewAccessRequest, applicant: User) -> None:
        viewer_role = normalize_role(viewer.role)
        applicant_role = normalize_role(applicant.role)
        req_type = req.request_type

        if req_type == REQ_VIEW_LIBRARY:
            if viewer_role not in (SUPER_ADMIN, ADMIN):
                raise ValueError("无权审核该申请")
            return

        if req_type == REQ_VIEW_ALL_MEETINGS:
            if viewer_role not in (SUPER_ADMIN, ADMIN):
                raise ValueError("无权审核该申请")
            return

        if req_type == REQ_DOWNLOAD_MEETINGS:
            if viewer_role == SUPER_ADMIN:
                return
            if viewer_role == ADMIN and bool(getattr(viewer, "approve_meeting_download", False)):
                return
            raise ValueError("无权审批会议下载权限申请")

        if req_type == REQ_VIEW_ROOT_MEETINGS:
            if viewer_role != SUPER_ADMIN:
                raise ValueError("仅超级管理员可审批该申请")
            if applicant_role != ADMIN:
                raise ValueError("申请人不是管理员")
            return

        if req_type == REQ_PROMOTE_ADMIN:
            if viewer_role != SUPER_ADMIN:
                raise ValueError("仅超级管理员可审批管理员升级申请")
            if applicant_role != USER:
                raise ValueError("申请人不是普通用户")
            return

        raise ValueError("未知申请类型")

    @staticmethod
    def review_access_request(
        db: Session,
        request_id: int,
        reviewer: User,
        approve: bool,
        review_note: str | None = None,
    ) -> ViewAccessRequest:
        if not can_review_access(reviewer):
            raise ValueError("无权审核申请")

        req = db.query(ViewAccessRequest).filter(ViewAccessRequest.id == request_id).first()
        if not req:
            raise ValueError("申请不存在")
        if req.status != "pending":
            raise ValueError("该申请已处理")

        applicant = db.query(User).filter(User.id == req.user_id).first()
        if not applicant:
            raise ValueError("申请人不存在")
        if should_hide_user_from(reviewer, applicant):
            raise ValueError("申请不存在")

        PermissionService._can_reviewer_handle(reviewer, req, applicant)

        req.status = "approved" if approve else "rejected"
        req.reviewer_id = reviewer.id
        req.review_note = review_note
        req.reviewed_at = datetime.now()

        if approve:
            if req.request_type == REQ_VIEW_LIBRARY:
                applicant.view_library = 1
            elif req.request_type == REQ_VIEW_ALL_MEETINGS:
                applicant.view_all_meetings = 1
            elif req.request_type == REQ_DOWNLOAD_MEETINGS:
                applicant.download_meetings = 1
            elif req.request_type == REQ_VIEW_ROOT_MEETINGS:
                applicant.view_root_meetings = 1
            elif req.request_type == REQ_PROMOTE_ADMIN:
                applicant.role = ADMIN
                applicant.view_library = 1
                applicant.view_all_meetings = 1

        db.commit()
        db.refresh(req)
        return req

    @staticmethod
    def get_settings(db: Session) -> dict:
        return {
            "block_upper_role_tasks": get_system_setting(
                db, SETTING_BLOCK_UPPER_TASKS, "true"
            ).lower()
            in ("1", "true", "yes"),
        }

    @staticmethod
    def update_settings(db: Session, viewer: User, block_upper_role_tasks: bool) -> dict:
        if not can_review_access(viewer):
            raise ValueError("无权修改系统权限设置")

        row = db.query(SystemSetting).filter(SystemSetting.key == SETTING_BLOCK_UPPER_TASKS).first()
        value = "true" if block_upper_role_tasks else "false"
        if row:
            row.value = value
        else:
            db.add(SystemSetting(key=SETTING_BLOCK_UPPER_TASKS, value=value))
        db.commit()
        return PermissionService.get_settings(db)

    @staticmethod
    def revoke_library_access(db: Session, user_id: int, reviewer: User) -> User:
        if not can_review_access(reviewer):
            raise ValueError("无权操作")
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("用户不存在")
        if normalize_role(user.role) != USER:
            raise ValueError("仅可撤销普通用户的查阅权限")
        user.view_library = 0
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def list_request_types_for_user(user: User) -> list[dict]:
        from app.constants.permissions import ALL_REQUEST_TYPES

        result = []
        for req_type in ALL_REQUEST_TYPES:
            ok, _ = can_apply_request_type(user, req_type)
            if ok:
                result.append(
                    {
                        "value": req_type,
                        "label": REQUEST_TYPE_LABELS.get(req_type, req_type),
                    }
                )
        return result
