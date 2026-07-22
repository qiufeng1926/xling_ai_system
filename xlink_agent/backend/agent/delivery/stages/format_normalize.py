"""格式规整：只调排版，不篡改语义。"""

from __future__ import annotations

from agent.answer import (
    ensure_knowledge_disclaimer,
    sanitize_public_answer,
    strip_pick_number_prompts,
)
from agent.delivery.types import MaterialStrength


def format_normalize(
    text: str,
    *,
    materials: MaterialStrength = MaterialStrength.EMPTY,
    force_disclaimer: bool = False,
) -> str:
    """分段清洗、去选号提示；弱材料时补声明。"""
    t = strip_pick_number_prompts(sanitize_public_answer(text or ""))
    if not t:
        return t
    if force_disclaimer or materials in {
        MaterialStrength.EMPTY,
        MaterialStrength.WEAK,
        MaterialStrength.OFF_TOPIC,
    }:
        t = ensure_knowledge_disclaimer(t)
    return t.strip()
