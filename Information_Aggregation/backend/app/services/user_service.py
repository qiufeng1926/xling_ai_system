from sqlalchemy.orm import Session

from app.constants.roles import ADMIN, MANAGEABLE_ROLES, SUPER_ADMIN
from app.models import User
from app.schemas.user import UserCreate, UserUpdate
from app.utils.access_control import normalize_role
from app.utils.security import get_password_hash
from app.utils.user_permissions import effective_permissions


class UserService:
    @staticmethod
    def list_users(db: Session, page: int, page_size: int) -> tuple[list[User], int]:
        query = db.query(User).order_by(User.id.asc())
        total = query.count()
        items = query.offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    @staticmethod
    def search_users(
        db: Session,
        keyword: str,
        limit: int = 10,
        exclude_username: str | None = None,
    ) -> list[User]:
        keyword = (keyword or "").strip()
        query = db.query(User).filter(User.status == 1)
        if exclude_username:
            query = query.filter(User.username != exclude_username)
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
        )
        db.add(user)
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
            view_all_meetings=1 if role == ADMIN else 0,
            view_root_meetings=0,
            view_all_root_meetings=0,
            download_meetings=0,
            approve_meeting_download=0,
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
                if data.view_all_meetings is None and not user.view_all_meetings:
                    user.view_all_meetings = 1

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
    def delete_user(db: Session, user_id: int, operator: User) -> None:
        user = UserService.get_user(db, user_id)
        if not user:
            raise ValueError("用户不存在")
        if user.id == operator.id:
            raise ValueError("不能删除自己")
        if normalize_role(user.role) == SUPER_ADMIN:
            raise ValueError("不能删除超级管理员")
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
        }
