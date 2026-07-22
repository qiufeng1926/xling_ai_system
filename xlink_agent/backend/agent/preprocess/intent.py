"""轻量意图识别：驱动交付模板与扩写策略（通用，非垂类特判）。"""

from __future__ import annotations

import re

from agent.answer import is_count_list_goal
from agent.delivery.types import DeliveryIntent
from agent.memory_policy import classify_intent as classify_office_intent


def classify_delivery_intent(goal: str) -> DeliveryIntent:
    """识别交付侧意图标签。"""
    g = (goal or "").strip()
    if not g:
        return DeliveryIntent.GENERAL

    if is_count_list_goal(g) or re.search(
        r"(推荐|盘点|清单|选型|对比).{0,12}(\d+\s*(?:本|个|条|款|篇|首|部)|几[本个条款])",
        g,
    ):
        return DeliveryIntent.LIST_RECOMMEND

    if re.search(
        r"(写一份|撰写|起草|方案|计划|提纲|大纲|实施步骤|落地路径)",
        g,
    ) and not re.search(r"\.(docx|xlsx|pdf|pptx)\b", g, re.I):
        return DeliveryIntent.PLAN_WRITE

    if re.search(
        r"(代码|脚本|函数|实现一段|python|javascript|sql\b|正则)",
        g,
        re.I,
    ):
        return DeliveryIntent.CODE_GEN

    office = classify_office_intent(g)
    if office == "chitchat":
        return DeliveryIntent.CHITCHAT
    if office == "file_process":
        return DeliveryIntent.FILE_PROCESS
    if office == "data_calc":
        return DeliveryIntent.DATA_CALC

    if office == "research" or re.search(
        r"(搜索|检索|调研|查一下|了解|介绍|分析|详细讲|是什么|为什么)",
        g,
    ):
        # 短问答更偏 open_qa；带调研口吻仍标 research
        if re.search(r"(调研|综述|对比分析|多角度|深入)", g):
            return DeliveryIntent.RESEARCH
        if len(g) <= 40 or re.search(r"(是什么|为什么|怎么理解|介绍一下)", g):
            return DeliveryIntent.OPEN_QA
        return DeliveryIntent.RESEARCH

    return DeliveryIntent.GENERAL
