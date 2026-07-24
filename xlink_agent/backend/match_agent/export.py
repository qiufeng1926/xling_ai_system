"""商单筛库结果导出（xlsx），字段均来自消息 metadata.influencers。"""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from sqlalchemy.orm import Session

from db.models import Message

PLATFORM_LABELS = {
    "douyin": "抖音",
    "xiaohongshu": "小红书",
    "kuaishou": "快手",
    "wechat": "微信",
}


def parse_influencers_meta(metadata_json: str | None) -> list[dict[str, Any]]:
    if not metadata_json:
        return []
    try:
        meta = json.loads(metadata_json)
    except Exception:
        return []
    if not isinstance(meta, dict):
        return []
    items = meta.get("influencers")
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict) and x.get("id") is not None]


def load_cards_for_export(
    db: Session,
    *,
    conversation_id: int,
    message_id: int | None = None,
) -> tuple[list[dict[str, Any]], int | None]:
    """返回 (cards, source_message_id)。默认取最近一条含卡片的助手消息。"""
    q = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.role == "assistant",
        )
        .order_by(Message.id.desc())
    )
    if message_id is not None:
        row = q.filter(Message.id == message_id).first()
        if not row:
            return [], None
        cards = parse_influencers_meta(row.metadata_json)
        return cards, row.id if cards else None

    for row in q.limit(50).all():
        cards = parse_influencers_meta(row.metadata_json)
        if cards:
            return cards, row.id
    return [], None


def cards_to_xlsx(cards: list[dict[str, Any]]) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "商单筛库结果"
    headers = [
        "排名",
        "匹配分",
        "昵称",
        "平台",
        "达人UID",
        "库内ID",
        "粉丝量",
        "互动率",
        "机构",
        "标签",
        "人设",
        "拍摄风格",
        "合作政策",
        "手机",
        "微信",
        "匹配说明",
    ]
    ws.append(headers)

    for card in cards:
        contact = card.get("contact") if isinstance(card.get("contact"), dict) else {}
        tags = card.get("tags") or []
        persona = card.get("persona_traits") or []
        styles = card.get("shooting_style") or []
        reasons = card.get("match_reasons") or []
        eng = card.get("engagement_rate")
        ws.append(
            [
                card.get("rank") or "",
                card.get("match_score") if card.get("match_score") is not None else "",
                card.get("nickname") or "",
                PLATFORM_LABELS.get(str(card.get("platform") or ""), card.get("platform") or ""),
                card.get("platform_uid") or "",
                card.get("id") or "",
                card.get("follower_count") or 0,
                float(eng) if eng is not None and eng != "" else "",
                card.get("agency_name") or "",
                "、".join(str(t) for t in tags[:12]),
                "、".join(str(t) for t in persona[:8]),
                "、".join(str(t) for t in styles[:8]),
                (card.get("cooperation_policy") or "")[:500],
                contact.get("phone") or "",
                contact.get("wechat") or "",
                "；".join(str(r) for r in reasons[:5]),
            ]
        )

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
