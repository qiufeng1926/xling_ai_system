from sqlalchemy.orm import Session

from app.constants.account_status import ACTIVE, OFFBOARDED, OFFBOARDING
from app.constants.auth import HIDDEN_SUPER_USERNAME
from app.constants.roles import ADMIN, MANAGEABLE_ROLES, SUPER_ADMIN, USER
from app.models import User
from app.schemas.user import UserCreate, UserUpdate
from app.utils.access_control import (
    apply_hidden_user_scope,
    hidden_super_user_ids,
    is_hidden_super_user,
    normalize_role,
    should_hide_user_from,
)
from app.utils.security import get_password_hash
from app.utils.user_permissions import effective_permissions


class UserService:
    @staticmethod
    def list_users(
        db: Session, page: int, page_size: int, viewer: User | None = None
    ) -> tuple[list[User], int]:
        query = db.query(User).order_by(User.id.asc())
        if viewer is not None:
            query = apply_hidden_user_scope(db, query, viewer, User.id)
        total = query.count()
        items = query.offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    @staticmethod
    def search_users(
        db: Session,
        keyword: str,
        limit: int = 10,
        exclude_username: str | None = None,
        viewer: User | None = None,
    ) -> list[User]:
        keyword = (keyword or "").strip()
        query = db.query(User).filter(User.status == 1, User.account_status == ACTIVE)
        if exclude_username:
            query = query.filter(User.username != exclude_username)
        if viewer is not None:
            query = apply_hidden_user_scope(db, query, viewer, User.id)
        elif exclude_username and exclude_username.lower() != HIDDEN_SUPER_USERNAME:
            hidden_ids = hidden_super_user_ids(db)
            if hidden_ids:
                query = query.filter(~User.id.in_(hidden_ids))
        if keyword:
            like = f"%{keyword}%"
            query = query.filter(
                (User.username.like(like)) | (User.nickname.like(like))
            )
        return query.order_by(User.username.asc()).limit(limit).all()

    @staticmethod
    def get_user(db: Session, user_id: int) -> User | None:
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def register_user(db: Session, data) -> User:
        from app.config import settings
        from app.constants.auth import RESERVED_USERNAMES
        from app.constants.roles import USER

        if not settings.ALLOW_PUBLIC_REGISTER:
            raise ValueError("当前未开放自助注册，请联系管理员创建账号")

        username = data.username.strip()
        nickname = (data.nickname or "").strip()
        if username.lower() in RESERVED_USERNAMES:
            raise ValueError("该用户名不可注册")
        admin_username = settings.ADMIN_USERNAME.strip().lower()
        if admin_username and username.lower() == admin_username:
            raise ValueError("该用户名不可注册")
        if not nickname:
            raise ValueError("昵称不能为空")

        exists = db.query(User).filter(User.username == username).first()
        if exists:
            raise ValueError("用户名已存在")

        user = User(
            username=username,
            password_hash=get_password_hash(data.password),
            nickname=nickname,
            role=USER,
            status=1,
            view_library=0,
            view_all_meetings=0,
            view_root_meetings=0,
            view_all_root_meetings=0,
            download_meetings=0,
            approve_meeting_download=0,
            approve_meeting_view=0,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def _feishu_docs_authorized(scope: str | None) -> bool:
        if not scope:
            return False
        granted = {part.strip() for part in scope.split() if part.strip()}
        drive_ok = bool(
            granted
            & {
                "drive:drive",
                "drive:drive:readonly",
                "space:document:retrieve",
            }
        )
        docx_ok = bool(
            granted
            & {
                "docx:document",
                "docx:document:create",
                "docx:document:readonly",
            }
        )
        return drive_ok and docx_ok

    @staticmethod
    def _feishu_minutes_authorized(scope: str | None) -> bool:
        if not scope:
            return False
        granted = {part.strip() for part in scope.split() if part.strip()}
        search_ok = "minutes:minutes.search:read" in granted
        read_ok = bool(
            granted
            & {
                "minutes:minutes",
                "minutes:minutes:readonly",
                "minutes:minutes.basic:read",
            }
        )
        artifacts_ok = "minutes:minutes.artifacts:read" in granted
        return search_ok and read_ok and artifacts_ok

    @staticmethod
    def get_feishu_bind_status(user: User) -> dict:
        from datetime import datetime, timezone

        bound = bool(user.feishu_open_id)
        token_valid = False
        if bound and user.feishu_access_token:
            if user.feishu_token_expires_at:
                expires = user.feishu_token_expires_at
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                token_valid = expires > datetime.now(timezone.utc) or bool(user.feishu_refresh_token)
            else:
                token_valid = True
        docs_authorized = UserService._feishu_docs_authorized(user.feishu_oauth_scope) if bound else False
        minutes_authorized = UserService._feishu_minutes_authorized(user.feishu_oauth_scope) if bound else False
        return {
            "bound": bound,
            "feishu_name": user.feishu_name if bound else None,
            "token_valid": token_valid,
            "docs_authorized": docs_authorized,
            "minutes_authorized": minutes_authorized,
            "oauth_scope": user.feishu_oauth_scope if bound else None,
            "portal_username": user.username,
            "portal_nickname": user.nickname or user.username,
        }

    @staticmethod
    def bind_feishu_to_user(
        db: Session,
        *,
        user_id: int,
        open_id: str,
        union_id: str | None,
        name: str,
        access_token: str,
        refresh_token: str | None = None,
        token_expires_at=None,
        oauth_scope: str | None = None,
    ) -> User:
        from app.config import settings

        if not settings.ALLOW_FEISHU_BIND:
            raise ValueError("当前未开放飞书绑定")

        open_id = open_id.strip()
        if not open_id:
            raise ValueError("飞书 open_id 不能为空")

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("用户不存在")
        if user.status != 1:
            raise ValueError("账号已禁用")

        other = db.query(User).filter(User.feishu_open_id == open_id, User.id != user_id).first()
        if other:
            raise ValueError("该飞书账号已绑定其他系统用户")

        nickname = (name or "").strip()
        user.feishu_name = nickname or user.feishu_name
        user.feishu_open_id = open_id
        user.feishu_union_id = union_id
        user.feishu_access_token = access_token
        user.feishu_refresh_token = refresh_token
        user.feishu_token_expires_at = token_expires_at
        if oauth_scope is not None:
            user.feishu_oauth_scope = (oauth_scope.strip() or None)
            if user.feishu_oauth_scope and len(user.feishu_oauth_scope) > 2048:
                user.feishu_oauth_scope = user.feishu_oauth_scope[:2048]
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def unbind_feishu(db: Session, user_id: int) -> User:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("用户不存在")
        user.feishu_open_id = None
        user.feishu_union_id = None
        user.feishu_name = None
        user.feishu_access_token = None
        user.feishu_refresh_token = None
        user.feishu_token_expires_at = None
        user.feishu_oauth_scope = None
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def get_feishu_token_bundle(db: Session, user_id: int) -> dict:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("用户不存在")
        if not user.feishu_open_id or not user.feishu_access_token:
            raise ValueError("用户尚未绑定飞书")
        return {
            "open_id": user.feishu_open_id,
            "union_id": user.feishu_union_id,
            "access_token": user.feishu_access_token,
            "refresh_token": user.feishu_refresh_token,
            "token_expires_at": user.feishu_token_expires_at,
            "oauth_scope": user.feishu_oauth_scope,
        }

    @staticmethod
    def update_feishu_tokens(
        db: Session,
        *,
        user_id: int,
        access_token: str,
        refresh_token: str | None = None,
        token_expires_at=None,
        oauth_scope: str | None = None,
    ) -> User:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("用户不存在")
        if not user.feishu_open_id:
            raise ValueError("用户尚未绑定飞书")
        user.feishu_access_token = access_token.strip()
        if refresh_token:
            user.feishu_refresh_token = refresh_token.strip()
        user.feishu_token_expires_at = token_expires_at
        if oauth_scope is not None:
            user.feishu_oauth_scope = (oauth_scope.strip() or None)
            if user.feishu_oauth_scope and len(user.feishu_oauth_scope) > 2048:
                user.feishu_oauth_scope = user.feishu_oauth_scope[:2048]
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def create_user(db: Session, data: UserCreate, operator: User) -> User:
        role = normalize_role(data.role)
        if role not in MANAGEABLE_ROLES:
            raise ValueError("只能创建管理员或普通用户")
        if role == ADMIN and not UserService._can_assign_admin(operator):
            raise ValueError("无权创建管理员账号")

        exists = db.query(User).filter(User.username == data.username).first()
        if exists:
            raise ValueError("用户名已存在")

        user = User(
            username=data.username,
            password_hash=get_password_hash(data.password),
            nickname=data.nickname or data.username,
            role=role,
            status=1,
            view_library=1 if role == ADMIN else 0,
            view_all_meetings=0,
            view_root_meetings=0,
            view_all_root_meetings=0,
            download_meetings=0,
            approve_meeting_download=0,
            approve_meeting_view=0,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def update_user(db: Session, user_id: int, data: UserUpdate, operator: User) -> User:
        user = UserService.get_user(db, user_id)
        if not user:
            raise ValueError("用户不存在")
        if should_hide_user_from(operator, user):
            raise ValueError("用户不存在")

        target_is_super = normalize_role(user.role) == SUPER_ADMIN
        if target_is_super and user.id != operator.id:
            raise ValueError("不能修改其他超级管理员")
        if user.id == operator.id and data.status == 0:
            raise ValueError("不能禁用自己")

        if data.role is not None:
            new_role = normalize_role(data.role)
            if new_role == SUPER_ADMIN:
                raise ValueError("不能通过此接口设置超级管理员角色")
            if target_is_super:
                raise ValueError("不能修改超级管理员角色")
            if new_role not in MANAGEABLE_ROLES:
                raise ValueError("无效的角色")
            if new_role == ADMIN and not UserService._can_assign_admin(operator):
                raise ValueError("无权设置管理员角色")
            old_role = normalize_role(user.role)
            user.role = new_role
            if new_role == ADMIN and old_role == USER:
                if data.view_library is None and not user.view_library:
                    user.view_library = 1

        if data.nickname is not None:
            user.nickname = data.nickname
        if data.status is not None:
            user.status = data.status

        if not target_is_super:
            UserService._apply_bool_field(user, "view_library", data.view_library)
            UserService._apply_bool_field(user, "view_all_meetings", data.view_all_meetings)
            UserService._apply_bool_field(user, "view_root_meetings", data.view_root_meetings)
            UserService._apply_bool_field(user, "download_meetings", data.download_meetings)
            UserService._apply_bool_field(user, "approve_meeting_download", data.approve_meeting_download)
            UserService._apply_bool_field(user, "approve_meeting_view", data.approve_meeting_view)

        if target_is_super and data.view_all_root_meetings is not None:
            user.view_all_root_meetings = 1 if data.view_all_root_meetings else 0

        if data.password:
            user.password_hash = get_password_hash(data.password)

        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def _apply_bool_field(user: User, field: str, value: bool | None) -> None:
        if value is None:
            return
        setattr(user, field, 1 if value else 0)

    @staticmethod
    def _detach_permission_request_users(db: Session, user: User) -> None:
        from app.models.permission import ViewAccessRequest

        db.query(ViewAccessRequest).filter(
            ViewAccessRequest.user_id == user.id,
            ViewAccessRequest.applicant_username.is_(None),
        ).update(
            {
                ViewAccessRequest.applicant_username: user.username,
                ViewAccessRequest.applicant_nickname: user.nickname,
            },
            synchronize_session=False,
        )
        db.query(ViewAccessRequest).filter(
            ViewAccessRequest.reviewer_id == user.id,
            ViewAccessRequest.reviewer_username.is_(None),
        ).update(
            {
                ViewAccessRequest.reviewer_username: user.username,
                ViewAccessRequest.reviewer_nickname: user.nickname,
            },
            synchronize_session=False,
        )
        db.query(ViewAccessRequest).filter(ViewAccessRequest.user_id == user.id).update(
            {ViewAccessRequest.user_id: None}, synchronize_session=False
        )
        db.query(ViewAccessRequest).filter(ViewAccessRequest.reviewer_id == user.id).update(
            {ViewAccessRequest.reviewer_id: None}, synchronize_session=False
        )

    @staticmethod
    def _cleanup_user_relations(db: Session, user_id: int) -> None:
        from app.models.collection import CollectedInfluencer, CollectionTask
        from app.models.match import MatchRequest, MatchResult

        user = db.query(User).filter(User.id == user_id).first()
        if user:
            UserService._detach_permission_request_users(db, user)

        task_ids = [
            row[0] for row in db.query(CollectionTask.id).filter(CollectionTask.user_id == user_id).all()
        ]
        if task_ids:
            db.query(CollectedInfluencer).filter(
                CollectedInfluencer.task_id.in_(task_ids)
            ).delete(synchronize_session=False)
            db.query(CollectionTask).filter(CollectionTask.id.in_(task_ids)).delete(
                synchronize_session=False
            )

        db.query(CollectedInfluencer).filter(CollectedInfluencer.reviewed_by == user_id).update(
            {CollectedInfluencer.reviewed_by: None}, synchronize_session=False
        )

        match_ids = [
            row[0] for row in db.query(MatchRequest.id).filter(MatchRequest.user_id == user_id).all()
        ]
        if match_ids:
            db.query(MatchResult).filter(MatchResult.request_id.in_(match_ids)).delete(
                synchronize_session=False
            )
            db.query(MatchRequest).filter(MatchRequest.id.in_(match_ids)).delete(
                synchronize_session=False
            )

    @staticmethod
    def delete_user(db: Session, user_id: int, operator: User) -> None:
        user = UserService.get_user(db, user_id)
        if not user:
            raise ValueError("用户不存在")
        if user.id == operator.id:
            raise ValueError("不能删除自己")
        if getattr(user, "account_status", ACTIVE) in (OFFBOARDING, OFFBOARDED):
            raise ValueError("离职相关账号请通过离职交接流程处理")
        if is_hidden_super_user(user):
            raise ValueError("不能删除系统内置超级管理员")
        if should_hide_user_from(operator, user):
            raise ValueError("用户不存在")
        target_is_super = normalize_role(user.role) == SUPER_ADMIN
        if target_is_super and not is_hidden_super_user(operator):
            raise ValueError("不能删除超级管理员")
        UserService._cleanup_user_relations(db, user_id)
        db.delete(user)
        db.commit()

    @staticmethod
    def _can_assign_admin(operator: User) -> bool:
        return normalize_role(operator.role) == SUPER_ADMIN

    @staticmethod
    def _stored_permissions(user: User) -> dict[str, bool]:
        return {
            "view_library": bool(getattr(user, "view_library", False)),
            "view_all_meetings": bool(getattr(user, "view_all_meetings", False)),
            "view_root_meetings": bool(getattr(user, "view_root_meetings", False)),
            "view_all_root_meetings": bool(getattr(user, "view_all_root_meetings", False)),
            "download_meetings": bool(getattr(user, "download_meetings", False)),
            "approve_meeting_download": bool(getattr(user, "approve_meeting_download", False)),
            "approve_meeting_view": bool(getattr(user, "approve_meeting_view", False)),
        }

    @staticmethod
    def to_out(user: User) -> dict:
        stored = UserService._stored_permissions(user)
        effective = effective_permissions(user)
        return {
            "id": user.id,
            "username": user.username,
            "nickname": user.nickname,
            "role": normalize_role(user.role),
            "status": user.status,
            **stored,
            "permissions": effective,
            "created_at": user.created_at,
            "feishu_bound": bool(user.feishu_open_id),
            "feishu_name": user.feishu_name if user.feishu_open_id else None,
            "account_status": getattr(user, "account_status", ACTIVE),
            "offboarded_at": getattr(user, "offboarded_at", None),
        }
