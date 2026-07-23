"""Agent 调度层：会话接入与模型/向量/工具之间的中枢。

子模块：
- SessionManager / PreProcessor / MemoryRetriever / ContextManager
- TaskStateMachine / ToolController / PromptBuilder / PostArchiver
入口：DispatchLayer.prepare_turn
"""

from agent.dispatch.layer import DispatchLayer, get_dispatch_layer
from agent.dispatch.types import (
    ContextBundle,
    DispatchQuery,
    DispatchRequest,
    MemoryHit,
    PromptPackage,
    SessionRuntime,
    TaskRuntimeStatus,
    TaskTransition,
    TurnPreparation,
)

__all__ = [
    "ContextBundle",
    "DispatchLayer",
    "DispatchQuery",
    "DispatchRequest",
    "MemoryHit",
    "PromptPackage",
    "SessionRuntime",
    "TaskRuntimeStatus",
    "TaskTransition",
    "TurnPreparation",
    "get_dispatch_layer",
]
