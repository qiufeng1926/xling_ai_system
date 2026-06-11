"""应用设置（持久化到 .env）"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth_utils import get_current_user
from config.config import (
    get_tingwu_diarization_speaker_count,
    set_tingwu_diarization_speaker_count,
)
from db.models import User
from utils.logger import get_logger

router = APIRouter()
logger = get_logger("settings_route")


class TingwuSpeakerCountRequest(BaseModel):
    mode: str = Field(..., pattern="^(auto|manual)$")
    speaker_count: int = Field(default=0, ge=0, le=100)


@router.get("/settings/tingwu-speaker-count")
def get_tingwu_speaker_count_setting(
    current_user: User = Depends(get_current_user),
):
    """获取实时转写会议人数（说话人分离）配置。"""
    count = get_tingwu_diarization_speaker_count()
    return {
        "success": True,
        "mode": "auto" if count == 0 else "manual",
        "speaker_count": count,
    }


@router.put("/settings/tingwu-speaker-count")
def update_tingwu_speaker_count_setting(
    body: TingwuSpeakerCountRequest,
    current_user: User = Depends(get_current_user),
):
    """保存会议人数设置到 .env，下次新建实时转写任务时生效。"""
    if body.mode == "auto":
        count = 0
    else:
        if body.speaker_count < 2:
            raise HTTPException(status_code=400, detail="手动设置时会议人数至少为 2 人")
        count = body.speaker_count

    saved = set_tingwu_diarization_speaker_count(count)
    logger.info(
        f"会议人数设置已更新: count={saved}, user={current_user.username}"
    )
    return {
        "success": True,
        "mode": "auto" if saved == 0 else "manual",
        "speaker_count": saved,
        "message": "会议人数设置已保存",
    }
