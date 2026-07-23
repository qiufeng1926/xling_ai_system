"""调度层中枢：串起会话 → 预处理 → 检索 → 上下文 → 任务状态 → 工具 → 组装。

不承担大模型推理 / 向量计算 / 业务工具执行；只做管控与报文组装。
"""

from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from agent.dispatch.context_manager import ContextManager
from agent.dispatch.memory_retriever import MemoryRetriever
from agent.dispatch.post_archiver import PostArchiver
from agent.dispatch.preprocessor import PreProcessor
from agent.dispatch.prompt_builder import PromptBuilder
from agent.dispatch.session_manager import SessionManager
from agent.dispatch.task_state_machine import TaskStateMachine
from agent.dispatch.tool_controller import ToolController
from agent.dispatch.types import DispatchRequest, TurnPreparation
from agent.entity_match import expand_goal_with_entities, merge_entity_hits_into_task_artifacts
from agent.inference.param_policy import params_for_profile
from utils.logger import get_logger

logger = get_logger("dispatch.layer")


class DispatchLayer:
    """设计稿 §2 总体执行流程（推理前半段 + 归档入口）。"""

    def __init__(
        self,
        *,
        session_manager: SessionManager | None = None,
        preprocessor: PreProcessor | None = None,
        memory_retriever: MemoryRetriever | None = None,
        context_manager: ContextManager | None = None,
        task_sm: TaskStateMachine | None = None,
        tool_controller: ToolController | None = None,
        prompt_builder: PromptBuilder | None = None,
        post_archiver: PostArchiver | None = None,
    ) -> None:
        self.sessions = session_manager or SessionManager()
        self.preprocessor = preprocessor or PreProcessor()
        self.memory = memory_retriever or MemoryRetriever()
        self.context = context_manager or ContextManager()
        self.task_sm = task_sm or TaskStateMachine()
        self.tools = tool_controller or ToolController()
        self.prompts = prompt_builder or PromptBuilder()
        self.archiver = post_archiver or PostArchiver()

    async def prepare_turn(
        self,
        db: Session,
        request: DispatchRequest,
        *,
        merge_tools_fn: Callable[[Session, int], tuple[list[str], str]],
        sanitize_fn: Callable[[str], str],
        looks_internal_fn: Callable[[str], bool],
    ) -> TurnPreparation:
        """推理前串行链路，对应设计稿步骤 1–7（不含 LLM 调用）。"""
        session = self.sessions.load_or_init(
            db, user_id=request.user_id, session_id=request.session_id
        )
        query = self.preprocessor.process(request.message, session.history)
        if query.debug.get("expanded"):
            logger.info(
                "dispatch followup expanded: %r -> %r",
                request.message[:40],
                query.expanded_goal[:160],
            )

        active_task, transition, effective_goal = self.task_sm.resolve(
            db,
            user_id=request.user_id,
            session_id=request.session_id,
            user_text=request.message,
            history=session.history,
            query_goal=query.expanded_goal,
            is_followup=query.is_followup,
            client_task_id=request.task_id,
        )

        memory_asm, hits, long_term = await self.memory.retrieve(
            db,
            user_id=request.user_id,
            session_id=request.session_id,
            user_text=request.message,
            history=session.history,
            active_task=active_task,
            effective_goal=effective_goal,
            transition=transition,
        )
        entity_result = memory_asm.entity_result
        effective_goal = expand_goal_with_entities(effective_goal, entity_result)
        if entity_result.ok:
            active_task.artifacts = merge_entity_hits_into_task_artifacts(
                active_task.artifacts, entity_result
            )

        # 画像以最终有效目标刷新（含任务根目标合并）
        from agent.preprocess import build_request_profile

        profile = build_request_profile(effective_goal)
        query.profile = profile
        query.fact_tier = str(getattr(getattr(profile, "tier", None), "value", query.fact_tier))
        query.delivery_intent = str(
            getattr(getattr(profile, "intent", None), "value", query.delivery_intent)
        )
        query.intent = str(getattr(profile, "office_intent", None) or query.intent)

        ctx = self.context.build(
            session=session,
            active_task=active_task,
            effective_goal=effective_goal,
            memory_hits=hits,
            window_history=memory_asm.window_history,
            sanitize_fn=sanitize_fn,
            looks_internal_fn=looks_internal_fn,
        )

        tools, skill_body = merge_tools_fn(db, request.user_id)
        tools = self.tools.filter_tools_for_intent(
            tools, query=query, transition=transition
        )
        contracts = self.tools.render_contracts(tools)
        system = self.prompts.build_react_system(
            tools=tools,
            tool_contracts=contracts,
            skill_body=skill_body,
            query=query,
            context=ctx,
            memory_system_block=memory_asm.system_memory_block,
            long_term_memory=long_term,
            transition=transition,
        )
        react_params = params_for_profile(profile, phase="react")
        prompt = self.prompts.build_package(
            system=system,
            dialog_messages=ctx.messages,
            tools=tools,
            temperature=float(getattr(react_params, "temperature", 0.2) or 0.2),
            meta={
                "transition": transition.value,
                "task_id": active_task.task_id,
                "soft": ctx.soft_triggered,
                "hard": ctx.hard_triggered,
            },
        )

        self.sessions.touch(
            session,
            active_task_id=active_task.task_id,
            status=self.task_sm.to_runtime_status(transition),
        )

        return TurnPreparation(
            request=request,
            session=session,
            query=query,
            transition=transition,
            active_task=active_task,
            effective_goal=effective_goal,
            memory_hits=hits,
            memory_asm=memory_asm,
            context=ctx,
            prompt=prompt,
            tools=tools,
            skill_body=skill_body,
            request_profile=profile,
            long_term_memory=long_term,
        )


_default_layer: DispatchLayer | None = None


def get_dispatch_layer() -> DispatchLayer:
    global _default_layer
    if _default_layer is None:
        _default_layer = DispatchLayer()
    return _default_layer
