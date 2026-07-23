"""调度层核心 DTO：接入层 ↔ 调度层 ↔（模型 / 工具 / 向量）边界。

标识三元组约定：
- user_id  ↔ 设计稿 userId（长期记忆隔离）
- session_id ↔ 设计稿 sessionId（= conversation_id，会话窗口隔离）
- task_id ↔ 设计稿 taskId（链式任务强绑定）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskTransition(str, Enum):
    CONTINUE = "continue"
    NEW = "new"
    SWITCH = "switch"
    CHITCHAT = "chitchat"


class TaskRuntimeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    COMPLETED = "completed"
    ABORTED = "aborted"


@dataclass
class DispatchRequest:
    """接入层标准请求。"""

    user_id: int
    session_id: int  # conversation_id
    message: str
    run_id: str = ""
    task_id: str | None = None  # 客户端可空，由状态机决定


@dataclass
class DispatchQuery:
    """PreProcessor 输出的结构化查询。"""

    raw: str
    cleaned: str
    expanded_goal: str
    entities: list[str] = field(default_factory=list)
    intent: str = "general"
    delivery_intent: str = ""
    fact_tier: str = "B"
    is_followup: bool = False
    profile: Any | None = None
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryHit:
    """召回片段：必须是结构化摘要，禁止超长原文直灌。"""

    text: str
    score: float
    source: str  # task_bind | entity | vector | long_term | summary
    task_id: str = ""
    summary_id: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionRuntime:
    """会话运行时（可落 Redis；P1 由 SessionManager 用 DB 装配）。"""

    user_id: int
    session_id: int
    active_task_id: str = ""
    task_status: TaskRuntimeStatus = TaskRuntimeStatus.PENDING
    history: list[Any] = field(default_factory=list)
    last_active_at: float = 0.0
    context_soft_ratio: float = 0.70
    context_hard_ratio: float = 0.90
    max_context_chars: int = 24000
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextBundle:
    """ContextManager 输出的分区上下文。"""

    permanent: list[str] = field(default_factory=list)
    retain: list[dict[str, str]] = field(default_factory=list)
    recalled: list[MemoryHit] = field(default_factory=list)
    messages: list[dict[str, str]] = field(default_factory=list)
    system_extra: str = ""
    char_used: int = 0
    soft_triggered: bool = False
    hard_triggered: bool = False


@dataclass
class PromptPackage:
    """送入大模型的标准请求包。"""

    system: str
    messages: list[dict[str, str]]
    tools: list[str] = field(default_factory=list)
    temperature: float = 0.2
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnPreparation:
    """调度层「推理前」完整产物，供 ReAct 循环消费。"""

    request: DispatchRequest
    session: SessionRuntime
    query: DispatchQuery
    transition: TaskTransition
    active_task: Any  # ActiveTask
    effective_goal: str
    memory_hits: list[MemoryHit] = field(default_factory=list)
    memory_asm: Any | None = None  # MemoryAssembly（兼容现有）
    context: ContextBundle | None = None
    prompt: PromptPackage | None = None
    tools: list[str] = field(default_factory=list)
    skill_body: str = ""
    request_profile: Any | None = None
    long_term_memory: str = ""
