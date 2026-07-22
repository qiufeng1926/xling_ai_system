"""交付流水线共享类型（第一期）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DeliveryIntent(str, Enum):
    """轻量意图标签：驱动模板与扩写策略，非产品垂类。"""

    LIST_RECOMMEND = "list_recommend"  # 推荐 N 本/个/款等计数清单
    OPEN_QA = "open_qa"  # 开放式问答 / 介绍 / 解释
    PLAN_WRITE = "plan_write"  # 方案 / 计划 / 提纲撰写
    CODE_GEN = "code_gen"  # 代码生成 / 脚本
    FILE_PROCESS = "file_process"  # 文档处理
    DATA_CALC = "data_calc"  # 计算统计
    CHITCHAT = "chitchat"  # 闲聊
    RESEARCH = "research"  # 调研检索类
    GENERAL = "general"


class FactRisk(str, Enum):
    """事实风险等级：驱动 temperature / 声明 / 重试预算。"""

    HIGH = "high_fact"  # 高事实风险：新闻数据、史实断言、精确数字
    NORMAL = "normal"
    LOW = "low"  # 闲聊 / 创意 / 主观偏好


class MaterialStrength(str, Enum):
    """检索材料对当前意图的可用强度。"""

    USABLE = "usable"
    WEAK = "weak"
    OFF_TOPIC = "off_topic"
    EMPTY = "empty"


class OutputAction(str, Enum):
    """后置决策动作。"""

    PASS = "pass"
    PASS_WITH_DISCLAIMER = "pass_with_disclaimer"
    RETRY_EXPAND = "retry_expand"
    RESCUE_DRAFT = "rescue_draft"
    REFUSE = "refuse"


@dataclass
class RequestProfile:
    """请求预处理产物：意图 + 风险 + 实体 + 检索 query。"""

    goal: str
    intent: DeliveryIntent = DeliveryIntent.GENERAL
    risk: FactRisk = FactRisk.NORMAL
    entities: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    office_intent: str = "general"  # 兼容 memory_policy.classify_intent
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeliveryContext:
    """单次 finalize 上下文。"""

    goal: str
    draft: str = ""
    thought: str = ""
    facts: list[str] = field(default_factory=list)
    profile: RequestProfile | None = None
    materials: MaterialStrength = MaterialStrength.EMPTY
    round_i: int = 0
    run_state: Any | None = None


@dataclass
class DeliveryResult:
    """流水线输出。"""

    text: str
    path: str = ""
    action: OutputAction = OutputAction.PASS
    retries: int = 0
    profile: RequestProfile | None = None
    materials: MaterialStrength = MaterialStrength.EMPTY
