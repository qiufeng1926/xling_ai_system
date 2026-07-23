"""会话管理：加载 / 初始化会话运行时。

P1：以 DB（conversation_id）为权威存储；接口预留 Redis 热缓存。
sessionId 在本系统中映射为 conversation_id。
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from agent.dispatch.types import SessionRuntime, TaskRuntimeStatus
from db.models import Conversation, ConversationTask, Message
from utils.logger import get_logger

logger = get_logger("dispatch.session")

TASK_STATUS_OPEN = "open"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_ABANDONED = "abandoned"


def _map_task_status(raw: str) -> TaskRuntimeStatus:
    if raw == TASK_STATUS_COMPLETED:
        return TaskRuntimeStatus.COMPLETED
    if raw == TASK_STATUS_ABANDONED:
        return TaskRuntimeStatus.ABORTED
    return TaskRuntimeStatus.RUNNING


class SessionManager:
    """根据 session_id 加载会话；不存在则由接入层先建 Conversation。"""

    def __init__(self, *, idle_ttl_sec: int = 3600) -> None:
        self.idle_ttl_sec = idle_ttl_sec
        # 进程内热缓存（多实例时替换为 Redis）
        self._hot: dict[int, SessionRuntime] = {}

    def load_or_init(
        self,
        db: Session,
        *,
        user_id: int,
        session_id: int,
        history_limit: int = 40,
    ) -> SessionRuntime:
        cached = self._hot.get(session_id)
        if cached and cached.user_id == user_id:
            if time.time() - cached.last_active_at < self.idle_ttl_sec:
                history = self._load_history(db, session_id, history_limit)
                cached.history = history
                cached.last_active_at = time.time()
                return cached

        conv = (
            db.query(Conversation)
            .filter(Conversation.id == session_id, Conversation.user_id == user_id)
            .first()
        )
        if not conv:
            # 接入层应已创建；此处仅防御
            logger.warning("session missing id=%s uid=%s", session_id, user_id)

        history = self._load_history(db, session_id, history_limit)
        open_task = (
            db.query(ConversationTask)
            .filter(
                ConversationTask.user_id == user_id,
                ConversationTask.conversation_id == session_id,
                ConversationTask.status == TASK_STATUS_OPEN,
            )
            .order_by(ConversationTask.created_at.desc())
            .first()
        )
        runtime = SessionRuntime(
            user_id=user_id,
            session_id=session_id,
            active_task_id=(open_task.task_id if open_task else "") or "",
            task_status=_map_task_status(open_task.status) if open_task else TaskRuntimeStatus.PENDING,
            history=history,
            last_active_at=time.time(),
            meta={"conversation_exists": bool(conv)},
        )
        self._hot[session_id] = runtime
        return runtime

    def touch(self, session: SessionRuntime, *, active_task_id: str = "", status: TaskRuntimeStatus | None = None) -> None:
        session.last_active_at = time.time()
        if active_task_id:
            session.active_task_id = active_task_id
        if status is not None:
            session.task_status = status
        self._hot[session.session_id] = session

    def release_if_idle(self, session_id: int) -> None:
        cached = self._hot.get(session_id)
        if not cached:
            return
        if time.time() - cached.last_active_at >= self.idle_ttl_sec:
            self._hot.pop(session_id, None)
            logger.info("session hot cache released id=%s", session_id)

    @staticmethod
    def _load_history(db: Session, session_id: int, limit: int) -> list[Any]:
        return (
            db.query(Message)
            .filter(Message.conversation_id == session_id)
            .order_by(Message.id.asc())
            .limit(limit)
            .all()
        )
