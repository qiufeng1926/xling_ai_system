"""通用 xlink-agent → 商单筛库智能体 的单向调用工具。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from match_agent.orchestrator import run_match_oneshot
from tools.portal_context import get_portal_bearer
from utils.logger import get_logger

logger = get_logger("call_influencer_match")


async def call_influencer_match(
    args: dict[str, Any],
    *,
    db: Session,
    user_id: int,
) -> dict[str, Any]:
    brief = str(args.get("brief") or args.get("query") or args.get("message") or "").strip()
    if not brief:
        return {"ok": False, "error": "call_influencer_match 需要 brief（商单正文）"}
    if not get_portal_bearer():
        return {
            "ok": False,
            "error": "缺少门户令牌，无法调用商单筛库智能体读取达人库",
        }
    try:
        result = await run_match_oneshot(db, user_id=user_id, brief=brief)
    except Exception as exc:
        logger.exception("call_influencer_match failed")
        return {"ok": False, "error": str(exc)}
    return result
