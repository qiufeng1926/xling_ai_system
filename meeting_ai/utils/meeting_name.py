"""会议名称解析：用户未填写时，用 AI 纪要主题 + 时间戳命名。"""
from __future__ import annotations

import re
from datetime import datetime

_TOPIC_LINE_RE = re.compile(r"^主题\s*[:：]\s*(.+)$", re.MULTILINE)
_TOPIC_PLACEHOLDER = "（概括本次会议核心议题，10～25 字；可参考已知会议名称）"


def _parse_at(value: datetime | str | None) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now()


def extract_topic_from_summary(summary: str | None) -> str | None:
    """从 Markdown 纪要首行「主题:」提取议题。"""
    if not summary:
        return None
    match = _TOPIC_LINE_RE.search(summary.strip())
    if not match:
        return None
    topic = match.group(1).strip()
    topic = re.sub(r"^[（(].*[）)]$", "", topic).strip()
    if not topic or topic == _TOPIC_PLACEHOLDER:
        return None
    return topic[:80]


def resolve_meeting_name(
    user_name: str | None,
    *,
    summary: str | None = None,
    visual_title: str | None = None,
    at: datetime | str | None = None,
) -> str:
    """
    用户已填写名称则原样使用；否则为「AI 主题_yyyyMMdd_HHmmss」。
    无纪要时主题为「会议」。
    """
    user = (user_name or "").strip()
    if user:
        return user[:255]

    dt = _parse_at(at)
    timestamp = dt.strftime("%Y%m%d_%H%M%S")
    topic = extract_topic_from_summary(summary)
    if not topic and visual_title:
        topic = visual_title.strip()
    if not topic:
        topic = "会议"
    topic = topic.replace("\n", " ").strip()
    return f"{topic}_{timestamp}"[:255]


def safe_filename_prefix(meeting_name: str | None) -> str:
    """将会议名称转为文件名安全前缀（含尾部下划线）；无名称时返回空串。"""
    safe = "".join(
        c for c in (meeting_name or "") if c.isalnum() or c in (" ", "-", "_")
    ).strip().replace(" ", "_")
    return f"{safe}_" if safe else ""
