"""任务状态机：CONTINUE / NEW / SWITCH / CHITCHAT。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from agent.dispatch.types import TaskRuntimeStatus, TaskTransition
from agent.memory_policy import classify_intent
from agent.task_binding import (
    BIND_CONTINUE,
    BIND_NEW,
    BIND_SWITCH,
    ActiveTask,
    expand_goal_with_task,
    resolve_task_binding,
)


class TaskStateMachine:
    """设计稿 §3.5：基于 taskId 与请求内容判定任务流转。"""

    def resolve(
        self,
        db: Session,
        *,
        user_id: int,
        session_id: int,
        user_text: str,
        history: list[Any],
        query_goal: str,
        is_followup: bool,
        client_task_id: str | None = None,
    ) -> tuple[ActiveTask, TaskTransition, str]:
        office_intent = classify_intent(user_text or "")
        # 自由闲聊：仍走绑定（保持会话连贯），但标记为 CHITCHAT 供下游弱检索
        active = resolve_task_binding(
            db,
            user_id=user_id,
            conversation_id=session_id,
            user_text=user_text,
            history=history,
            effective_goal=query_goal,
            forced_followup=is_followup,
        )
        # 客户端显式续绑：与会话活跃 task 一致时强制 continue 语义
        if (
            client_task_id
            and active.task_id
            and client_task_id == active.task_id
            and active.bind_mode != BIND_SWITCH
        ):
            active.bind_mode = BIND_CONTINUE

        if office_intent == "chitchat" and active.bind_mode == BIND_NEW:
            transition = TaskTransition.CHITCHAT
        elif active.bind_mode == BIND_CONTINUE:
            transition = TaskTransition.CONTINUE
        elif active.bind_mode == BIND_SWITCH:
            transition = TaskTransition.SWITCH
        else:
            transition = TaskTransition.NEW

        effective = expand_goal_with_task(query_goal, active)
        return active, transition, effective

    @staticmethod
    def to_runtime_status(transition: TaskTransition, *, waiting: bool = False) -> TaskRuntimeStatus:
        if waiting:
            return TaskRuntimeStatus.WAITING_USER
        if transition == TaskTransition.CHITCHAT:
            return TaskRuntimeStatus.RUNNING
        return TaskRuntimeStatus.RUNNING
