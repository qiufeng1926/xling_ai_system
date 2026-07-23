"""动态 Prompt 组装：按意图 / 材料强度 / A·B·C 档位拼接 system / user 块。"""

from __future__ import annotations

from agent.delivery.types import DeliveryIntent, FactTier, MaterialStrength, RequestProfile
from agent.prompts.registry import load_template


def assemble_synthesize_system(*, profile: RequestProfile | None = None) -> str:
    """综合总结器 system prompt。"""
    base = load_template("synthesize_grounded")
    if not base:
        base = "你是通用信息整理编辑。优先有依据、少幻觉，其次可读性。只输出中文正文。"
    parts = [base]
    if profile and profile.intent == DeliveryIntent.LIST_RECOMMEND:
        extra = load_template("finalize_list")
        if extra:
            parts.append("# 清单详写补强\n" + extra)
    if profile and profile.tier == FactTier.A:
        anti = load_template("anti_hallucination_list")
        if anti:
            parts.append("# 防幻觉基础指令（A 类）\n" + anti)
    return "\n\n".join(parts)


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
        if profile and profile.tier == FactTier.A:
            anti = load_template("anti_hallucination_list")
            if anti:
                parts.append(anti)
            parts.append(
                "A 类约束：禁止脱离检索/核验材料自由扩充具名条目；"
                "无法确认的条目直接舍弃，不要为凑数臆造。"
            )
    elif materials == MaterialStrength.USABLE:
        parts.append(
            "特别要求（接地）：以检索材料与草稿已有条目组织答案；"
            "可概括材料；禁止补充材料与草稿都未出现的冷门具体数据；"
            "禁止把清单套话当成具体条目。"
        )
        if profile and profile.tier == FactTier.A:
            anti = load_template("anti_hallucination_list")
            if anti:
                parts.append(anti)
        if force_expand or (profile and profile.intent == DeliveryIntent.LIST_RECOMMEND):
            if profile and profile.tier == FactTier.A:
                parts.append(
                    "草稿若偏标题清单：仅为材料/草稿中可确认的条目补写 2～4 句；"
                    "材料不够时宁可少写并文首声明，禁止注水假条目。"
                )
            else:
                parts.append(
                    "草稿若偏标题清单：为每条补写 2～4 句；材料不够可用常识级简介并文首标明未充分核实；"
                    "禁止把答案缩成材料里能核验的一两项。"
                )
    return "\n".join(parts).strip()


def assemble_fallback_system() -> str:
    t = load_template("fallback_honest")
    return t or "材料不足时给出诚实短答，文首标明未充分核实。"


def assemble_react_base_addon(*, profile: RequestProfile | None = None) -> str:
    """可选附加到 ReAct system（不替换现有长 prompt，仅作增强片段）。"""
    parts: list[str] = []
    base = load_template("react_base")
    if base:
        parts.append(base)
    if profile and profile.tier == FactTier.A:
        anti = load_template("anti_hallucination_list")
        if anti:
            parts.append(anti)
        parts.append(
            "路由提示（A 类）：须先检索或书目核验再 finish；"
            "禁止无 Observation 时编造具名清单；temperature 保持克制。"
        )
    elif profile and profile.tier == FactTier.C:
        parts.append(
            "路由提示（C 类）：闲聊/创意场景，无需强制检索，保持自然表达。"
        )
    return "\n\n".join(p for p in parts if p).strip()
