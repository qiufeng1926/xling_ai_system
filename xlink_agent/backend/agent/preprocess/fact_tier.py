"""事实约束档位 A/B/C：通用轻量意图标签（非垂类特判）。"""

from __future__ import annotations

import re

from agent.delivery.types import DeliveryIntent, FactRisk, FactTier


# A 类：高事实风险「具名清单」——书目/文献/著作/法条/史实名录等
_TIER_A_ENTITY_LIST_RE = re.compile(
    r"("
    r"书|书籍|书单|图书|小说|著作|文献|论文|读物|必读|"
    r"法条|法规|法律条文|法典|司法解释|"
    r"名人|历史人物|史实|名录|作家|诗人|学者|导演|"
    r"传记|专辑|影片|电影|剧作|经典作品"
    r")"
)

_TIER_A_LIST_ACT_RE = re.compile(
    r"(推荐|盘点|清单|列出|列举|整理|汇总|给我|有哪些|哪几).{0,24}"
    r"(本|部|篇|条|首|个|种|份)?"
)

_TIER_C_RE = re.compile(
    r"("
    r"闲聊|聊聊|讲个笑话|写一首诗|写首诗|脑洞|虚构故事|编个故事|"
    r"角色扮演|创意写作|随便聊聊|开个玩笑|段子|打油诗|"
    r"想象一下|假如你是|陪我聊天|你好啊|在吗"
    r")"
)


def classify_fact_tier(
    goal: str,
    *,
    intent: DeliveryIntent | None = None,
    risk: FactRisk | None = None,
) -> FactTier:
    """打出 A/B/C 事实约束档位。"""
    g = (goal or "").strip()
    if not g:
        return FactTier.B

    # C：闲聊 / 创意 / 脑洞
    if intent == DeliveryIntent.CHITCHAT or _TIER_C_RE.search(g):
        return FactTier.C

    # A：高事实风险具名清单
    if intent == DeliveryIntent.LIST_RECOMMEND or _TIER_A_LIST_ACT_RE.search(g):
        if _TIER_A_ENTITY_LIST_RE.search(g):
            return FactTier.A

    # 实时/精确事实问答也升到 A（与 FactRisk.HIGH 对齐的增强约束）
    if risk == FactRisk.HIGH and intent in {
        DeliveryIntent.OPEN_QA,
        DeliveryIntent.RESEARCH,
        DeliveryIntent.LIST_RECOMMEND,
        DeliveryIntent.GENERAL,
    }:
        # 纯天气/股价等短问答走 A 的强制检索，但不走清单后置
        return FactTier.A

    return FactTier.B


def sync_risk_with_tier(risk: FactRisk, tier: FactTier) -> FactRisk:
    """档位回写风险：A→至少 HIGH，C→LOW，B 保持原风险。"""
    if tier == FactTier.A:
        return FactRisk.HIGH
    if tier == FactTier.C:
        return FactRisk.LOW
    return risk
