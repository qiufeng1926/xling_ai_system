"""动态 Prompt 组装：按意图 / 材料强度拼接 system / user 块。"""

from __future__ import annotations

from agent.delivery.types import DeliveryIntent, MaterialStrength, RequestProfile
from agent.prompts.registry import load_template


def assemble_synthesize_system(*, profile: RequestProfile | None = None) -> str:
    """综合总结器 system prompt。"""
    base = load_template("synthesize_grounded")
    if not base:
        # 回退：避免空 system
        base = "你是通用信息整理编辑。优先有依据、少幻觉，其次可读性。只输出中文正文。"
    if profile and profile.intent == DeliveryIntent.LIST_RECOMMEND:
        extra = load_template("finalize_list")
        if extra:
            return f"{base}\n\n# 清单详写补强\n{extra}"
    return base


def assemble_expand_hint(
    *,
    profile: RequestProfile | None,
    materials: MaterialStrength,
    force_expand: bool = False,
) -> str:
    """用户消息中的扩写/接地提示块。"""
    parts: list[str] = []
    if materials in {MaterialStrength.EMPTY, MaterialStrength.OFF_TOPIC, MaterialStrength.WEAK} or force_expand:
        expand = load_template("synthesize_expand")
        if expand:
            parts.append(expand)
        if profile and profile.intent == DeliveryIntent.LIST_RECOMMEND:
            fl = load_template("finalize_list")
            if fl:
                parts.append(fl)
    elif materials == MaterialStrength.USABLE:
        parts.append(
            "特别要求（接地）：以检索材料与草稿已有条目组织答案；"
            "可概括材料；禁止补充材料与草稿都未出现的冷门具体数据；"
            "禁止把清单套话当成具体条目。"
        )
        if force_expand or (profile and profile.intent == DeliveryIntent.LIST_RECOMMEND):
            parts.append(
                "草稿若偏标题清单：为每条补写 2～4 句；材料不够可用常识级简介并文首标明未充分核实；"
                "禁止把答案缩成材料里能核验的一两项。"
            )
    return "\n".join(parts).strip()


def assemble_fallback_system() -> str:
    t = load_template("fallback_honest")
    return t or "材料不足时给出诚实短答，文首标明未充分核实。"


def assemble_react_base_addon() -> str:
    """可选附加到 ReAct system（不替换现有长 prompt，仅作增强片段）。"""
    return load_template("react_base")
