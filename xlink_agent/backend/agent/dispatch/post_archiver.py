"""异步归档：语义切片入向量库 + 长期记忆偏好抽取。

不阻塞接口响应：优先 create_task；失败则同步降级（保证不丢）。
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.orm import Session

from agent.memory_service import maybe_update_profile_from_dialog
from agent.session_memory import maybe_compact_conversation
from agent.task_binding import update_task_after_turn
from utils.logger import get_logger

logger = get_logger("dispatch.archiver")


class PostArchiver:
    """设计稿 §3.8。"""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()

    def schedule_turn_archive(
        self,
        db: Session,
        *,
        user_id: int,
        session_id: int,
        task_id: str,
        run_id: str,
        user_text: str,
        answer_preview: str,
        artifacts: list[str] | None = None,
        sync_fallback: bool = True,
    ) -> None:
        """应答返回后调用；内部尽量异步。"""

        async def _job() -> None:
            try:
                update_task_after_turn(
                    db,
                    task_id=task_id,
                    user_id=user_id,
                    run_id=run_id,
                    artifacts=artifacts or [],
                    answer_preview=answer_preview or "",
                )
                await self._compact_and_index(
                    db,
                    user_id=user_id,
                    session_id=session_id,
                    task_id=task_id,
                )
                maybe_update_profile_from_dialog(db, user_id, user_text)
            except Exception:
                logger.exception(
                    "post archive failed session=%s task=%s", session_id, task_id[:8] if task_id else ""
                )

        try:
            loop = asyncio.get_running_loop()
            t = loop.create_task(_job())
            self._tasks.add(t)
            t.add_done_callback(self._tasks.discard)
        except RuntimeError:
            if sync_fallback:
                # 无事件循环时同步执行（测试 / 脚本）
                update_task_after_turn(
                    db,
                    task_id=task_id,
                    user_id=user_id,
                    run_id=run_id,
                    artifacts=artifacts or [],
                    answer_preview=answer_preview or "",
                )

    async def archive_turn_await(
        self,
        db: Session,
        *,
        user_id: int,
        session_id: int,
        task_id: str,
        run_id: str,
        user_text: str,
        answer_preview: str,
        artifacts: list[str] | None = None,
    ) -> None:
        """需要确定性完成时用（与现网 orchestrator 行为对齐）。"""
        update_task_after_turn(
            db,
            task_id=task_id,
            user_id=user_id,
            run_id=run_id,
            artifacts=artifacts or [],
            answer_preview=answer_preview or "",
        )
        await self._compact_and_index(
            db,
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
        )
        maybe_update_profile_from_dialog(db, user_id, user_text)

    async def index_tool_observation(
        self,
        *,
        user_id: int,
        session_id: int,
        task_id: str,
        tool: str,
        result: dict[str, Any],
        run_id: str = "",
    ) -> None:
        if not isinstance(result, dict) or result.get("error"):
            return
        if tool in {"browser_screenshot", "memory_recall"}:
            return
        try:
            import json

            from agent.vector_memory import index_tool_step

            blob = json.dumps(result, ensure_ascii=False)[:1500]
            if len(blob) < 12:
                return
            await index_tool_step(
                user_id=user_id,
                conversation_id=session_id,
                task_id=task_id or "",
                tool=tool,
                observation=blob,
                run_id=run_id,
            )
        except Exception:
            logger.exception("tool_step index failed tool=%s", tool)

    @staticmethod
    async def _compact_and_index(
        db: Session,
        *,
        user_id: int,
        session_id: int,
        task_id: str,
    ) -> None:
        try:
            from db.models import Message

            hist = (
                db.query(Message)
                .filter(Message.conversation_id == session_id)
                .order_by(Message.id.asc())
                .limit(80)
                .all()
            )
            created = maybe_compact_conversation(
                db,
                user_id=user_id,
                conversation_id=session_id,
                history=hist,
                task_id=task_id or "",
            )
            if created:
                from agent.vector_memory import index_conversation_summaries

                await index_conversation_summaries(created)
        except Exception:
            logger.exception(
                "session compact failed session=%s uid=%s", session_id, user_id
            )
