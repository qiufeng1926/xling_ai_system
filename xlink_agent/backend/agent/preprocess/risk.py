"""事实风险分级：驱动推理超参与输出声明。"""

from __future__ import annotations

import re

from agent.delivery.types import DeliveryIntent, FactRisk


_HIGH_FACT_RE = re.compile(
    r"("
    r"股价|汇率|天气|气温|实时|最新|今天|昨日|同比|环比|百分之|"
    r"\d{4}\s*年|公元|确切|准确数据|统计公报|官方数据|"
    r"谁发明|几月几日|伤亡|确诊"
    r")"
)

_LOW_RISK_RE = re.compile(
    r"(闲聊|聊聊|讲个笑话|写一首诗|脑洞|虚构故事|角色扮演|你好|谢谢)"
)


def classify_fact_risk(goal: str, *, intent: DeliveryIntent | None = None) -> FactRisk:
    """高事实风险 / 普通 / 低风险。"""
    g = (goal or "").strip()
    if not g:
        return FactRisk.NORMAL

    if intent == DeliveryIntent.CHITCHAT or _LOW_RISK_RE.search(g):
        return FactRisk.LOW

    if intent == DeliveryIntent.CODE_GEN and not _HIGH_FACT_RE.search(g):
        return FactRisk.LOW

    if _HIGH_FACT_RE.search(g):
        return FactRisk.HIGH

    # 具名清单（书目/文献/法条/史实等）默认高事实风险
    if intent == DeliveryIntent.LIST_RECOMMEND:
        if re.search(
            r"(书|书籍|书单|著作|文献|论文|法条|法规|名人|史实|名录|作家|经典)",
            g,
        ):
            return FactRisk.HIGH
        if re.search(r"(权威|官方|销量|评分必须|最新榜单|实时)", g):
            return FactRisk.HIGH
        return FactRisk.NORMAL

    if intent in {DeliveryIntent.RESEARCH, DeliveryIntent.OPEN_QA, DeliveryIntent.PLAN_WRITE}:
        return FactRisk.NORMAL

    return FactRisk.NORMAL
