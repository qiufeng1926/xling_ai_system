"""协作会议房间：数据库读写"""

from __future__ import annotations

import secrets
import string
import uuid
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from config.config import collab_max_participants, collab_max_recorders
from db.models import CollaborativeRoom, RoomInvitation, RoomParticipant, User

ROOM_CODE_CHARS = string.ascii_uppercase + string.digits
ROOM_CODE_LENGTH = 6


def _normalize_username(username: str) -> str:
    return (username or "").strip()


def _username_match(column, username: str):
    """用户名比较（忽略大小写；写入时已 strip）"""
    return func.lower(column) == _normalize_username(username).lower()


def _find_invitation(
    db: Session,
    room_id: int,
    username: str,
    *,
    status: str | tuple[str, ...] | None = None,
) -> RoomInvitation | None:
    q = db.query(RoomInvitation).filter(
        RoomInvitation.room_id == room_id,
        _username_match(RoomInvitation.invitee_username, username),
    )
    if status is not None:
        if isinstance(status, tuple):
            q = q.filter(RoomInvitation.status.in_(status))
        else:
            q = q.filter(RoomInvitation.status == status)
    return q.first()


def _gen_room_code() -> str:
    return "".join(secrets.choice(ROOM_CODE_CHARS) for _ in range(ROOM_CODE_LENGTH))


def create_room(db: Session, host: User, meeting_name: str) -> CollaborativeRoom:
    meeting_name = (meeting_name or "").strip()
    if not meeting_name:
        raise ValueError("会议名称不能为空")

    for _ in range(10):
        code = _gen_room_code()
        if not db.query(CollaborativeRoom).filter(CollaborativeRoom.room_code == code).first():
            break
    else:
        raise RuntimeError("无法生成唯一房间码")

    file_id = str(uuid.uuid4())
    room = CollaborativeRoom(
        room_code=code,
        file_id=file_id,
        host_username=host.username,
        host_user_id=host.id,
        meeting_name=meeting_name,
        status="waiting",
        merged_transcript="",
    )
    db.add(room)
    db.flush()

    db.add(
        RoomParticipant(
            room_id=room.id,
            username=host.username,
            nickname=host.nickname or host.username,
            role="host",
            joined_at=datetime.now(),
        )
    )
    db.commit()
    db.refresh(room)
    return room


def get_room_by_code(db: Session, room_code: str) -> CollaborativeRoom | None:
    return (
        db.query(CollaborativeRoom)
        .filter(CollaborativeRoom.room_code == room_code.strip().upper())
        .first()
    )


def _resolve_role(db: Session, room: CollaborativeRoom, username: str) -> str | None:
    username = _normalize_username(username)
    if _normalize_username(room.host_username).lower() == username.lower():
        return "host"
    inv = _find_invitation(db, room.id, username, status="accepted")
    if inv:
        return inv.role
    part = (
        db.query(RoomParticipant)
        .filter(
            RoomParticipant.room_id == room.id,
            _username_match(RoomParticipant.username, username),
        )
        .first()
    )
    if part:
        return part.role
    return None


def can_access_room(db: Session, room: CollaborativeRoom, username: str) -> bool:
    username = _normalize_username(username)
    if _normalize_username(room.host_username).lower() == username.lower():
        return True
    inv = _find_invitation(db, room.id, username, status=("pending", "accepted"))
    return inv is not None


def invite_users(
    db: Session,
    room: CollaborativeRoom,
    inviter_username: str,
    invitees: list[dict],
) -> list[RoomInvitation]:
    if inviter_username != room.host_username:
        raise ValueError("仅主持人可邀请参与者")
    if room.status not in ("waiting", "live"):
        raise ValueError("当前会议状态不可邀请")

    created: list[RoomInvitation] = []
    for item in invitees:
        username = _normalize_username(item.get("username") or "")
        role = (item.get("role") or "recorder").strip().lower()
        if not username:
            continue
        if _normalize_username(room.host_username).lower() == username.lower():
            continue
        if role not in ("recorder", "viewer"):
            raise ValueError(f"无效角色: {role}")
        if db.query(User).filter(User.username == username).first() is None:
            # 允许邀请尚未在 meeting_ai 出现过的门户用户（首次加入时 shadow）
            pass

        existing = _find_invitation(db, room.id, username)
        if existing:
            if existing.status == "declined":
                existing.status = "pending"
                existing.role = role
                existing.invited_by = inviter_username
                existing.responded_at = None
                created.append(existing)
            elif existing.status == "pending":
                existing.role = role
                created.append(existing)
            continue

        inv = RoomInvitation(
            room_id=room.id,
            invitee_username=username,
            invited_by=inviter_username,
            role=role,
            status="pending",
        )
        db.add(inv)
        created.append(inv)

    db.commit()
    return created


def accept_invitation(db: Session, room: CollaborativeRoom, username: str) -> RoomInvitation:
    username = _normalize_username(username)
    inv = _find_invitation(db, room.id, username, status="pending")
    if not inv:
        raise ValueError("没有待接受的邀请")

    inv.status = "accepted"
    inv.responded_at = datetime.now()
    stored_username = _normalize_username(inv.invitee_username)

    part = (
        db.query(RoomParticipant)
        .filter(
            RoomParticipant.room_id == room.id,
            _username_match(RoomParticipant.username, stored_username),
        )
        .first()
    )
    if not part:
        user = db.query(User).filter(_username_match(User.username, stored_username)).first()
        nickname = user.nickname if user else stored_username
        db.add(
            RoomParticipant(
                room_id=room.id,
                username=stored_username,
                nickname=nickname or stored_username,
                role=inv.role,
            )
        )
    db.commit()
    db.refresh(inv)
    return inv


def join_room(db: Session, room: CollaborativeRoom, user: User) -> dict:
    if room.status in ("completed", "cancelled", "ending"):
        raise ValueError("会议已结束")

    username = _normalize_username(user.username)
    if not can_access_room(db, room, username):
        raise ValueError("无权加入该会议")

    # 待接受邀请的用户进入房间时自动接受（计划：pending→accept）
    pending_inv = _find_invitation(db, room.id, username, status="pending")
    if pending_inv:
        accept_invitation(db, room, pending_inv.invitee_username)

    role = _resolve_role(db, room, username)
    if role is None:
        raise ValueError("请先接受邀请")

    participant_count = (
        db.query(RoomParticipant)
        .filter(RoomParticipant.room_id == room.id, RoomParticipant.left_at.is_(None))
        .count()
    )
    if participant_count >= collab_max_participants:
        raise ValueError(f"会议人数已达上限（{collab_max_participants}）")

    part = (
        db.query(RoomParticipant)
        .filter(
            RoomParticipant.room_id == room.id,
            _username_match(RoomParticipant.username, username),
        )
        .first()
    )
    if not part:
        part = RoomParticipant(
            room_id=room.id,
            username=username,
            nickname=user.nickname or username,
            role=role,
        )
        db.add(part)
    else:
        part.username = username
        part.nickname = user.nickname or username
        part.left_at = None
    part.joined_at = datetime.now()
    db.commit()

    return build_room_state(db, room, username)


def start_room(db: Session, room: CollaborativeRoom, username: str) -> CollaborativeRoom:
    if username != room.host_username:
        raise ValueError("仅主持人可开始会议")
    if room.status != "waiting":
        raise ValueError("会议已开始或已结束")
    room.status = "live"
    room.started_at = datetime.now()
    db.commit()
    db.refresh(room)
    return room


def end_room(db: Session, room: CollaborativeRoom, username: str) -> CollaborativeRoom:
    if username != room.host_username:
        raise ValueError("仅主持人可结束会议")
    if room.status not in ("waiting", "live"):
        raise ValueError("会议已结束")
    room.status = "ending"
    room.ended_at = datetime.now()
    db.commit()
    db.refresh(room)
    return room


def complete_room(db: Session, room: CollaborativeRoom, merged_transcript: str) -> CollaborativeRoom:
    room.merged_transcript = merged_transcript
    room.status = "completed"
    if not room.ended_at:
        room.ended_at = datetime.now()
    db.commit()
    db.refresh(room)
    return room


def append_transcript(db: Session, room: CollaborativeRoom, line: str) -> str:
    line = (line or "").strip()
    if not line:
        return room.merged_transcript or ""
    current = room.merged_transcript or ""
    if current and not current.endswith("\n"):
        current += "\n"
    room.merged_transcript = current + line + "\n"
    db.commit()
    return room.merged_transcript


def build_room_state(db: Session, room: CollaborativeRoom, viewer_username: str) -> dict:
    participants = (
        db.query(RoomParticipant)
        .filter(RoomParticipant.room_id == room.id)
        .order_by(RoomParticipant.id.asc())
        .all()
    )
    invitations = (
        db.query(RoomInvitation)
        .filter(RoomInvitation.room_id == room.id)
        .order_by(RoomInvitation.created_at.desc())
        .all()
    )
    my_role = _resolve_role(db, room, viewer_username)
    return {
        "room": room.to_dict(include_transcript=True),
        "my_role": my_role,
        "participants": [p.to_dict() for p in participants],
        "invitations": [i.to_dict() for i in invitations],
    }


def list_my_rooms(db: Session, username: str) -> dict:
    username = _normalize_username(username)
    hosted = (
        db.query(CollaborativeRoom)
        .filter(_username_match(CollaborativeRoom.host_username, username))
        .order_by(CollaborativeRoom.created_at.desc())
        .limit(50)
        .all()
    )
    invited_ids = [
        r[0]
        for r in db.query(RoomInvitation.room_id)
        .filter(
            _username_match(RoomInvitation.invitee_username, username),
            RoomInvitation.status == "accepted",
        )
        .all()
    ]
    joined = []
    if invited_ids:
        joined = (
            db.query(CollaborativeRoom)
            .filter(CollaborativeRoom.id.in_(invited_ids))
            .order_by(CollaborativeRoom.created_at.desc())
            .limit(50)
            .all()
        )
    pending = (
        db.query(RoomInvitation)
        .filter(
            _username_match(RoomInvitation.invitee_username, username),
            RoomInvitation.status == "pending",
        )
        .order_by(RoomInvitation.created_at.desc())
        .all()
    )
    pending_rooms = []
    for inv in pending:
        room = db.query(CollaborativeRoom).filter(CollaborativeRoom.id == inv.room_id).first()
        if room and room.status in ("waiting", "live"):
            pending_rooms.append({**inv.to_dict(), "room": room.to_dict()})

    return {
        "hosted": [r.to_dict() for r in hosted],
        "joined": [
            r.to_dict()
            for r in joined
            if _normalize_username(r.host_username).lower() != username.lower()
        ],
        "pending_invitations": pending_rooms,
    }


def count_active_recorders(db: Session, room_id: int) -> int:
    return (
        db.query(RoomParticipant)
        .filter(
            RoomParticipant.room_id == room_id,
            RoomParticipant.role.in_(("host", "recorder")),
            RoomParticipant.left_at.is_(None),
        )
        .count()
    )


def can_start_recording(db: Session, room: CollaborativeRoom, username: str) -> bool:
    role = _resolve_role(db, room, username)
    if role not in ("host", "recorder"):
        return False
    if role == "viewer":
        return False
    # 限制同时录音人数在 runtime 层更准确；此处仅校验角色
    return room.status == "live" or (room.status == "waiting" and username == room.host_username)


def max_recorders() -> int:
    return collab_max_recorders
