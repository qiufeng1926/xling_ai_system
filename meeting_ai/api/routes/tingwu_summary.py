"""听悟大模型摘要 API"""

import json
import os

from fastapi import APIRouter, Depends

from api.auth_utils import get_current_user
from config.config import output_dir
from db.models import User
from db.session import check_meeting_access, get_meeting_by_file_id
from utils.logger import get_logger

router = APIRouter()
logger = get_logger("tingwu_summary_route")


def _parse_tingwu_summarization(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _load_tingwu_from_file(file_path: str | None) -> dict | None:
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _find_tingwu_file_by_file_id(summaries_dir: str, file_id: str) -> str | None:
    if not os.path.isdir(summaries_dir):
        return None
    for name in os.listdir(summaries_dir):
        if not name.endswith("_tingwu.json"):
            continue
        if file_id in name:
            return os.path.join(summaries_dir, name)
    return None


@router.get("/meetings/{file_id}/tingwu-summary")
async def get_tingwu_summary(file_id: str, current_user: User = Depends(get_current_user)):
    """获取听悟大模型摘要（全文摘要、发言总结、问答回顾、思维导图）"""
    exists, allowed = check_meeting_access(file_id, current_user)
    if not exists:
        return {"success": False, "error": "会议不存在"}
    if not allowed:
        return {"success": False, "error": "无权查看该会议"}

    meeting = get_meeting_by_file_id(file_id)
    meeting_name = None
    status = None
    summarization = None
    file_path = None

    if meeting:
        meeting_name = meeting.meeting_name
        status = meeting.tingwu_summarization_status
        file_path = meeting.tingwu_summarization_file_path
        summarization = _parse_tingwu_summarization(meeting.tingwu_summarization)

    if summarization is None:
        summaries_dir = os.path.join(output_dir, "summaries")
        found = file_path or _find_tingwu_file_by_file_id(summaries_dir, file_id)
        if found:
            file_path = found
            summarization = _load_tingwu_from_file(found)
            if summarization and not status:
                status = "completed"

    if summarization is None and status not in ("failed", "skipped"):
        status = status or "pending"

    return {
        "success": True,
        "file_id": file_id,
        "meeting_name": meeting_name,
        "tingwu_summarization_status": status,
        "tingwu_summarization_file": file_path,
        "summarization": summarization,
        "has_content": bool(summarization),
    }
