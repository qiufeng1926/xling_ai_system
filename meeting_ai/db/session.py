"""
数据库会话管理
"""
from contextlib import contextmanager
from datetime import datetime, timedelta

from sqlalchemy import or_, and_, false
from sqlalchemy.orm import Session
from db.models import (
    init_database,
    get_session_factory,
    Meeting,
    User,
    PermissionRequest,
    MeetingDownloadLog,
    MeetingViewRequest,
    MeetingDownloadRequest,
)
from config.config import (
    database_url,
    seed_admin_password,
    seed_default_users_on_startup,
    seed_root_password,
)
from utils.logger import get_logger
from api.permissions import ROOT_MEETING_VIEW_DAYS, can_access_meeting, can_download_meeting
from utils.hidden_user import hidden_super_user_ids, is_hidden_super_user

logger = get_logger("database")

# 初始化数据库引擎和会话工厂
engine = init_database(database_url)
SessionFactory = get_session_factory(engine)


def _resolve_seed_password(env_value: str, label: str) -> str:
    import secrets
    import string

    if env_value and env_value.strip():
        return env_value.strip()
    pwd = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
    logger.warning(
        f"未配置 {label}，已生成随机密码（请查看日志并尽快修改）: {pwd}"
    )
    return pwd


def seed_default_users(session: Session) -> list[str]:
    """创建初始管理员账号；密码来自环境变量或随机生成。"""
    from utils.password import hash_password

    root_pwd = _resolve_seed_password(seed_root_password, "SEED_ROOT_PASSWORD")
    admin_pwd = _resolve_seed_password(seed_admin_password, "SEED_ADMIN_PASSWORD")

    defaults = [
        {
            "username": "root",
            "nickname": "超级管理员",
            "password": root_pwd,
            "role": "root",
            "can_view_all": True,
        },
        {
            "username": "admin",
            "nickname": "管理员",
            "password": admin_pwd,
            "role": "admin",
            "can_view_all": True,
        },
    ]
    created: list[str] = []
    for item in defaults:
        existing = session.query(User).filter(User.username == item["username"]).first()
        if not existing:
            session.add(
                User(
                    username=item["username"],
                    nickname=item["nickname"],
                    password_hash=hash_password(item["password"]),
                    role=item["role"],
                    can_view_all=item["can_view_all"],
                    can_view_all_roots=False,
                )
            )
            created.append(item["username"])
            logger.info(f"默认用户已创建: {item['username']}")
        else:
            if not existing.nickname:
                existing.nickname = item["nickname"]
    return created


if seed_default_users_on_startup:
    try:
        _seed_session = SessionFactory()
        try:
            seed_default_users(_seed_session)
            _seed_session.commit()
        finally:
            _seed_session.close()
    except Exception as e:
        logger.warning(f"默认用户初始化跳过: {e}")


@contextmanager
def get_db_session() -> Session:
    """获取数据库会话的上下文管理器"""
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"数据库操作失败，已回滚: {str(e)}", exc_info=True)
        raise
    finally:
        session.close()


async def save_meeting_to_db_async(meeting_data: dict) -> None:
    """在线程池中写入数据库，避免阻塞 WebSocket / 其他 API 事件循环"""
    from utils.executors import run_io
    await run_io(save_meeting_to_db, meeting_data)


def save_meeting_to_db(meeting_data: dict) -> Meeting:
    """
    保存会议记录到数据库
    
    Args:
        meeting_data: 会议数据字典
        
    Returns:
        Meeting: 保存的会议记录对象
    """
    with get_db_session() as session:
        meeting = Meeting(
            file_id=meeting_data['file_id'],
            user_id=meeting_data.get('user_id'),
            meeting_name=meeting_data.get('meeting_name'),
            original_filename=meeting_data.get('original_filename'),
            meeting_type=meeting_data.get('meeting_type', 'batch'),
            audio_file_path=meeting_data.get('audio_file_path'),
            transcript_file_path=meeting_data['transcript_file_path'],
            summary_file_path=meeting_data.get('summary_file_path'),
            transcript=meeting_data['transcript'],
            summary=meeting_data.get('summary'),
            summary_visual=meeting_data.get('summary_visual'),
            summary_visual_status=meeting_data.get('summary_visual_status'),
            tingwu_task_id=meeting_data.get('tingwu_task_id'),
            tingwu_summarization=meeting_data.get('tingwu_summarization'),
            tingwu_summarization_status=meeting_data.get('tingwu_summarization_status'),
            tingwu_summarization_file_path=meeting_data.get('tingwu_summarization_file_path'),
            transcript_length=meeting_data.get('transcript_length', len(meeting_data['transcript'])),
            summary_length=meeting_data.get('summary_length', len(meeting_data.get('summary', '')) if meeting_data.get('summary') else 0),
            audio_duration=meeting_data.get('audio_duration'),
            asr_duration_ms=meeting_data.get('asr_duration_ms'),
            llm_duration_ms=meeting_data.get('llm_duration_ms'),
            total_duration_ms=meeting_data.get('total_duration_ms'),
            status=meeting_data.get('status', 'completed'),
            error_message=meeting_data.get('error_message'),
            is_collaborative=meeting_data.get('is_collaborative', False),
            room_code=meeting_data.get('room_code'),
            host_username=meeting_data.get('host_username'),
        )
        session.add(meeting)
        logger.info(f"会议记录已保存到数据库: file_id={meeting_data['file_id']}")
        return meeting


def update_meeting_status(file_id: str, status: str, error_message: str = None):
    """
    更新会议状态
    
    Args:
        file_id: 文件ID
        status: 新状态
        error_message: 错误信息（可选）
    """
    with get_db_session() as session:
        meeting = session.query(Meeting).filter(Meeting.file_id == file_id).first()
        if meeting:
            meeting.status = status
            if error_message:
                meeting.error_message = error_message
            logger.info(f"会议状态已更新: file_id={file_id}, status={status}")
        else:
            logger.warning(f"未找到会议记录: file_id={file_id}")


def update_meeting_summaries(
    file_id: str,
    *,
    summary: str | None,
    summary_visual: str | None = None,
    summary_visual_status: str | None = None,
    summary_file_path: str | None = None,
    llm_duration_ms: int | None = None,
) -> bool:
    """更新已有会议的 AI 总结字段（不改动转写原文）"""
    with get_db_session() as session:
        meeting = session.query(Meeting).filter(Meeting.file_id == file_id).first()
        if not meeting:
            logger.warning(f"未找到会议记录: file_id={file_id}")
            return False
        meeting.summary = summary
        meeting.summary_length = len(summary) if summary else 0
        if summary_visual is not None:
            meeting.summary_visual = summary_visual
        if summary_visual_status is not None:
            meeting.summary_visual_status = summary_visual_status
        if summary_file_path is not None:
            meeting.summary_file_path = summary_file_path
        if llm_duration_ms is not None:
            meeting.llm_duration_ms = llm_duration_ms
        meeting.status = 'completed'
        meeting.error_message = None
        logger.info(f"会议总结已更新: file_id={file_id}, summary_length={meeting.summary_length}")
        return True


def _detach_instance(session: Session, instance):
    """在会话关闭前加载属性并分离，避免 DetachedInstanceError"""
    if instance is None:
        return None
    for column in instance.__table__.columns:
        getattr(instance, column.name)
    session.expunge(instance)
    return instance


def get_meeting_by_file_id(file_id: str) -> Meeting | None:
    """
    根据file_id获取会议记录
    
    Args:
        file_id: 文件ID
        
    Returns:
        Meeting: 会议记录对象，不存在则返回None
    """
    with get_db_session() as session:
        meeting = session.query(Meeting).filter(Meeting.file_id == file_id).first()
        return _detach_instance(session, meeting)


def user_can_access_meeting(file_id: str, viewer: User) -> bool:
    """在同一会话内校验用户是否有权查看会议（会议不存在视为无权限）"""
    exists, allowed = check_meeting_access(file_id, viewer)
    return exists and allowed


def check_meeting_access(file_id: str, viewer: User) -> tuple[bool, bool]:
    """返回 (会议是否存在, 是否有权查看)"""
    with get_db_session() as session:
        meeting = session.query(Meeting).filter(Meeting.file_id == file_id).first()
        if not meeting:
            return False, False
        owner = None
        if meeting.user_id:
            owner = session.query(User).filter(User.id == meeting.user_id).first()
        return True, can_access_meeting(viewer, meeting, owner, session=session)


def get_meeting_owner(user_id: int | None) -> User | None:
    """获取会议创建者"""
    if user_id is None:
        return None
    with get_db_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        return _detach_instance(session, user)


def _other_root_user_ids(session: Session, viewer: User) -> list[int]:
    ids = [
        r[0] for r in session.query(User.id).filter(
            User.role == 'root',
            User.id != viewer.id,
        ).all()
    ]
    if not is_hidden_super_user(viewer):
        for hid in hidden_super_user_ids(session):
            if hid not in ids:
                ids.append(hid)
    return ids


def _hidden_meeting_owner_ids(session: Session, viewer: User) -> list[int]:
    if is_hidden_super_user(viewer):
        return []
    return hidden_super_user_ids(session)


def _non_collaborative_meeting_access(session: Session, viewer: User):
    """非协作会议的可见性条件（不含 is_collaborative=True 的记录）。"""
    non_collab = Meeting.is_collaborative == False

    if viewer.is_root():
        if viewer.can_view_all_roots:
            return non_collab
        other_root_ids = _other_root_user_ids(session, viewer)
        conditions = [
            Meeting.user_id == viewer.id,
            Meeting.user_id.is_(None),
        ]
        if other_root_ids:
            conditions.append(
                and_(Meeting.user_id.isnot(None), ~Meeting.user_id.in_(other_root_ids))
            )
        else:
            conditions.append(Meeting.user_id.isnot(None))
        return and_(non_collab, or_(*conditions))

    if viewer.role == "admin":
        root_ids = [r[0] for r in session.query(User.id).filter(User.role == "root").all()]
        hidden_ids = _hidden_meeting_owner_ids(session, viewer)
        cutoff = datetime.now() - timedelta(days=ROOT_MEETING_VIEW_DAYS)
        conditions = [
            Meeting.user_id == viewer.id,
            Meeting.user_id.is_(None),
        ]
        if root_ids:
            conditions.append(
                and_(Meeting.user_id.isnot(None), ~Meeting.user_id.in_(root_ids))
            )
        else:
            conditions.append(Meeting.user_id.isnot(None))
        if viewer.can_view_root_meetings and root_ids:
            visible_root_ids = [rid for rid in root_ids if rid not in hidden_ids]
            if visible_root_ids:
                conditions.append(
                    and_(Meeting.user_id.in_(visible_root_ids), Meeting.created_at >= cutoff)
                )
        return and_(non_collab, or_(*conditions))

    if viewer.can_view_all:
        hidden_ids = _hidden_meeting_owner_ids(session, viewer)
        if hidden_ids:
            return and_(non_collab, or_(Meeting.user_id.is_(None), ~Meeting.user_id.in_(hidden_ids)))
        return non_collab

    return and_(non_collab, Meeting.user_id == viewer.id)


def _meeting_list_query(session: Session, viewer: User):
    """会议列表：展示全部记录（仍排除隐身超管账号的会议）。"""
    query = session.query(Meeting)
    hidden_ids = _hidden_meeting_owner_ids(session, viewer)
    if hidden_ids:
        query = query.filter(or_(Meeting.user_id.is_(None), ~Meeting.user_id.in_(hidden_ids)))
    return query


def _apply_viewer_meeting_filter(query, session: Session, viewer: User):
    """按用户角色过滤可见会议；协作会议仅参会人员可见。"""
    from services.collaborative_service import participant_collaborative_file_ids

    collab_file_ids = participant_collaborative_file_ids(session, viewer.username)
    if collab_file_ids:
        collab_access = and_(
            Meeting.is_collaborative == True,
            Meeting.file_id.in_(collab_file_ids),
        )
    else:
        collab_access = false()

    non_collab_access = _non_collaborative_meeting_access(session, viewer)
    return query.filter(or_(collab_access, non_collab_access))


def _latest_meeting_view_request_map(
    session: Session,
    viewer_id: int,
    file_ids: list[str],
) -> dict[str, str]:
    """返回 file_id -> 最新申请状态（pending/approved/rejected）"""
    if not file_ids:
        return {}
    rows = (
        session.query(MeetingViewRequest)
        .filter(
            MeetingViewRequest.user_id == viewer_id,
            MeetingViewRequest.file_id.in_(file_ids),
        )
        .order_by(MeetingViewRequest.created_at.desc())
        .all()
    )
    result: dict[str, str] = {}
    for row in rows:
        if row.file_id not in result:
            result[row.file_id] = row.status
    return result


def _latest_meeting_download_request_map(
    session: Session,
    viewer_id: int,
    file_ids: list[str],
) -> dict[str, str]:
    if not file_ids:
        return {}
    rows = (
        session.query(MeetingDownloadRequest)
        .filter(
            MeetingDownloadRequest.user_id == viewer_id,
            MeetingDownloadRequest.file_id.in_(file_ids),
        )
        .order_by(MeetingDownloadRequest.created_at.desc())
        .all()
    )
    result: dict[str, str] = {}
    for row in rows:
        if row.file_id not in result:
            result[row.file_id] = row.status
    return result


def get_all_meetings(
    limit: int = 100,
    offset: int = 0,
    start_date: str = None,
    end_date: str = None,
    viewer: User = None,
    user_id: int = None,
    can_view_all: bool = False,
) -> tuple[list[dict], int]:
    """
    获取会议记录（分页，支持日期筛选与权限过滤）。
    返回 (当前页列表, 符合条件的总条数)。
    """
    with get_db_session() as session:
        query = session.query(Meeting)

        if viewer is not None:
            query = _meeting_list_query(session, viewer)
        elif not can_view_all and user_id is not None:
            query = query.filter(Meeting.user_id == user_id)
        elif not can_view_all:
            query = query.filter(Meeting.user_id.is_(None))

        if start_date:
            try:
                from datetime import datetime as dt
                start_dt = dt.strptime(start_date, "%Y-%m-%d")
                query = query.filter(Meeting.created_at >= start_dt)
            except ValueError:
                logger.warning(f"无效的开始日期格式: {start_date}")

        if end_date:
            try:
                from datetime import datetime as dt, timedelta
                end_dt = dt.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                query = query.filter(Meeting.created_at < end_dt)
            except ValueError:
                logger.warning(f"无效的结束日期格式: {end_date}")

        total = query.count()
        meetings = (
            query.order_by(Meeting.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        items: list[dict] = []
        request_status_map: dict[str, str] = {}
        download_request_status_map: dict[str, str] = {}
        if viewer is not None:
            file_ids = [m.file_id for m in meetings]
            request_status_map = _latest_meeting_view_request_map(session, viewer.id, file_ids)
            download_request_status_map = _latest_meeting_download_request_map(session, viewer.id, file_ids)
        for meeting in meetings:
            row = meeting.to_list_dict()
            owner = None
            if meeting.user_id:
                owner = session.query(User).filter(User.id == meeting.user_id).first()
            if viewer is not None:
                allowed = can_access_meeting(viewer, meeting, owner, session=session)
                row["can_access"] = allowed
                row["can_download"] = can_download_meeting(viewer, meeting, owner, session=session)
                if viewer.is_root():
                    # 超级管理员无需单条审批；不展示历史申请状态
                    row["access_request_status"] = None
                    row["download_request_status"] = None
                    if not allowed:
                        row["preview"] = ""
                elif not allowed:
                    row["preview"] = ""
                    row["access_request_status"] = request_status_map.get(meeting.file_id)
                else:
                    row["access_request_status"] = None
                if not viewer.is_root():
                    if row["can_download"]:
                        row["download_request_status"] = None
                    else:
                        row["download_request_status"] = download_request_status_map.get(meeting.file_id)
            else:
                row["can_access"] = True
                row["can_download"] = True
                row["access_request_status"] = None
                row["download_request_status"] = None
            items.append(row)
        return items, total


def _remove_file_if_exists(path: str | None):
    import os
    if path and os.path.isfile(path):
        try:
            os.remove(path)
            logger.info(f"已删除文件: {path}")
        except OSError as e:
            logger.warning(f"删除文件失败: {path}, {e}")


def delete_meeting(file_id: str) -> bool:
    """删除会议记录（仅数据库）"""
    with get_db_session() as session:
        meeting = session.query(Meeting).filter(Meeting.file_id == file_id).first()
        if meeting:
            session.delete(meeting)
            logger.info(f"会议记录已删除: file_id={file_id}")
            return True
        logger.warning(f"未找到会议记录: file_id={file_id}")
        return False


def delete_meeting_with_files(file_id: str) -> bool:
    """删除会议记录及关联磁盘文件"""
    with get_db_session() as session:
        meeting = session.query(Meeting).filter(Meeting.file_id == file_id).first()
        if not meeting:
            logger.warning(f"未找到会议记录: file_id={file_id}")
            return False
        paths = [
            meeting.audio_file_path,
            meeting.transcript_file_path,
            meeting.summary_file_path,
        ]
        session.delete(meeting)
        session.flush()

    for path in paths:
        _remove_file_if_exists(path)
    logger.info(f"会议记录及文件已删除: file_id={file_id}")
    return True


def log_meeting_download(
    session: Session,
    *,
    user_id: int,
    meeting_name: str,
    export_type: str,
    file_id: str | None = None,
    meeting_user_id: int | None = None,
) -> None:
    """记录用户下载/导出会议文件"""
    name = (meeting_name or '').strip() or '未命名会议'
    entry = MeetingDownloadLog(
        user_id=user_id,
        file_id=file_id,
        meeting_name=name[:255],
        export_type=export_type,
        meeting_user_id=meeting_user_id,
    )
    session.add(entry)
    session.commit()

