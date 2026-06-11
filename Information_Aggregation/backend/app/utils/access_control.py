"""三级权限访问控制"""

from __future__ import annotations

from sqlalchemy.orm import Query, Session

from app.constants.roles import ADMIN, LEGACY_OPERATOR, ROLE_LEVEL, SUPER_ADMIN, USER
from app.models import User

SETTING_BLOCK_UPPER_TASKS = "block_upper_role_tasks"


def normalize_role(role: str | None) -> str:
    if not role or role == LEGACY_OPERATOR:
        return USER
    if role == "admin":
        return ADMIN
    return role


def role_level(user: User) -> int:
    return ROLE_LEVEL.get(normalize_role(user.role), 1)


def is_super_admin(user: User) -> bool:
    return normalize_role(user.role) == SUPER_ADMIN


def is_admin(user: User) -> bool:
    return normalize_role(user.role) == ADMIN


def is_user(user: User) -> bool:
    return normalize_role(user.role) == USER


def is_admin_or_above(user: User) -> bool:
    return role_level(user) >= ROLE_LEVEL[ADMIN]


def can_manage_users(user: User) -> bool:
    return is_super_admin(user)


def can_review_access(user: User) -> bool:
    return is_admin_or_above(user)


def can_manage_platform_sessions(user: User) -> bool:
    return is_admin_or_above(user)


def can_view_full_library(user: User) -> bool:
    if is_admin_or_above(user):
        return True
    return bool(getattr(user, "view_library", False))


def can_manage_tags(user: User) -> bool:
    return is_admin_or_above(user)


def can_use_match(user: User) -> bool:
    return is_admin_or_above(user)


def can_manage_agencies(user: User) -> bool:
    return is_admin_or_above(user)


def can_review_collected(user: User, task_owner_id: int, task_owner_role: str) -> bool:
    if task_owner_id == user.id:
        return True
    if is_super_admin(user):
        return True
    if is_admin(user):
        return role_level_by_name(task_owner_role) <= ROLE_LEVEL[USER]
    return task_owner_id == user.id


def role_level_by_name(role: str | None) -> int:
    return ROLE_LEVEL.get(normalize_role(role), 1)


def can_view_task(db: Session, viewer: User, task_user_id: int, task_owner: User | None = None) -> bool:
    if task_user_id == viewer.id:
        return True

    owner = task_owner or db.query(User).filter(User.id == task_user_id).first()
    if not owner:
        return False

    if is_super_admin(viewer):
        return True

    owner_role = normalize_role(owner.role)
    if owner_role == SUPER_ADMIN:
        return False

    if is_admin(viewer):
        return True

    return False


def apply_task_query_scope(db: Session, query: Query, viewer: User) -> Query:
    """兼容旧调用"""
    from app.models import CollectionTask

    if query.column_descriptions[0]["entity"] is CollectionTask:
        return task_query_for_viewer(db, viewer)
    return query


def task_query_for_viewer(db: Session, viewer: User):
    from sqlalchemy import or_

    from app.models import CollectionTask

    query = db.query(CollectionTask)
    if is_super_admin(viewer):
        return query

    if is_admin(viewer):
        super_admin_ids = [
            row[0] for row in db.query(User.id).filter(User.role == SUPER_ADMIN).all()
        ]
        if super_admin_ids:
            return query.filter(
                or_(
                    CollectionTask.user_id == viewer.id,
                    ~CollectionTask.user_id.in_(super_admin_ids),
                )
            )
        return query

    return query.filter(CollectionTask.user_id == viewer.id)


def collected_query_for_viewer(db: Session, viewer: User, *, reviewed_by_self: bool = False):
    from sqlalchemy import or_

    from app.models import CollectionTask, CollectedInfluencer

    query = db.query(CollectedInfluencer)
    if is_super_admin(viewer):
        q = query
    else:
        q = query.join(CollectionTask, CollectedInfluencer.task_id == CollectionTask.id)
        if is_admin(viewer):
            super_admin_ids = [
                row[0] for row in db.query(User.id).filter(User.role == SUPER_ADMIN).all()
            ]
            if super_admin_ids:
                q = q.filter(
                    or_(
                        CollectionTask.user_id == viewer.id,
                        ~CollectionTask.user_id.in_(super_admin_ids),
                    )
                )
        else:
            q = q.filter(CollectionTask.user_id == viewer.id)

    if reviewed_by_self and is_user(viewer):
        q = q.filter(CollectedInfluencer.reviewed_by == viewer.id)
    return q


def match_query_for_viewer(db: Session, viewer: User):
    from app.models import MatchRequest

    query = db.query(MatchRequest)
    if is_super_admin(viewer):
        return query
    if is_admin(viewer):
        super_admin_ids = [
            row[0] for row in db.query(User.id).filter(User.role == SUPER_ADMIN).all()
        ]
        if super_admin_ids:
            return query.filter(~MatchRequest.user_id.in_(super_admin_ids))
        return query
    return query.filter(MatchRequest.user_id == viewer.id)


def influencer_ids_for_user(db: Session, user_id: int) -> set[int]:
    """普通用户可查看的达人 ID（自己采集且自己审核通过）"""
    from app.models import CollectedInfluencer, CollectionTask

    rows = (
        db.query(CollectedInfluencer.influencer_id)
        .join(CollectionTask)
        .filter(
            CollectionTask.user_id == user_id,
            CollectedInfluencer.review_status == "approved",
            CollectedInfluencer.reviewed_by == user_id,
            CollectedInfluencer.influencer_id.isnot(None),
        )
        .all()
    )
    return {r[0] for r in rows if r[0]}


def get_system_setting(db: Session, key: str, default: str = "true") -> str:
    from app.models.permission import SystemSetting

    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return row.value if row else default


def is_block_upper_tasks(db: Session) -> bool:
    return get_system_setting(db, SETTING_BLOCK_UPPER_TASKS, "true").lower() in ("1", "true", "yes")
