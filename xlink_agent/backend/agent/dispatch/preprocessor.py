"""请求预处理：清洗 / 实体 / 意图 / 追问识别 → DispatchQuery。"""

from __future__ import annotations

from typing import Any

from agent.answer import expand_selection_followup, sanitize_public_answer
from agent.dispatch.types import DispatchQuery
from agent.memory_policy import expand_dialog_followup, is_dialog_followup
from agent.preprocess import build_request_profile
from agent.preprocess.query_rewrite import clean_goal_text


class PreProcessor:
    """设计稿 §3.2：输出结构化查询对象。"""

    def process(
        self,
        user_text: str,
        history: list[Any],
        *,
        draft: str = "",
    ) -> DispatchQuery:
        raw = (user_text or "").strip()
        cleaned = clean_goal_text(raw) or raw

        expanded = expand_selection_followup(raw, history)
        if not expanded:
            expanded = expand_dialog_followup(
                raw, history, sanitize_fn=sanitize_public_answer
            )
        is_followup = bool(expanded)
        if not is_followup and len(history) >= 2:
            prev_user = ""
            for item in reversed(history[:-1] if history else []):
                role = getattr(item, "role", None) or (
                    item.get("role") if isinstance(item, dict) else None
                )
                content = getattr(item, "content", None) or (
                    item.get("content") if isinstance(item, dict) else ""
                )
                if role == "user":
                    prev_user = content or ""
                    break
            is_followup = bool(prev_user) and is_dialog_followup(raw, prev_user)

        expanded_goal = (expanded or cleaned).strip()
        # 画像以展开后目标为准（续作/澄清可看到完整语境）
        profile = build_request_profile(expanded_goal, draft=draft)
        entities = [str(e) for e in (getattr(profile, "entities", None) or []) if e]

        return DispatchQuery(
            raw=raw,
            cleaned=cleaned,
            expanded_goal=expanded_goal,
            entities=entities,
            intent=str(getattr(profile, "office_intent", None) or "general"),
            delivery_intent=str(getattr(getattr(profile, "intent", None), "value", "") or ""),
            fact_tier=str(getattr(getattr(profile, "tier", None), "value", "B") or "B"),
            is_followup=is_followup,
            profile=profile,
            debug={"expanded": bool(expanded)},
        )
