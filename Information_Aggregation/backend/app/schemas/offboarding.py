from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class OffboardingApplyRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    last_work_day: date | None = None


class OffboardingCompleteRequest(BaseModel):
    handover_user_id: int = Field(..., ge=1)


class OffboardingRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    operator_id: int | None
    handover_user_id: int | None
    status: str
    reason: str | None
    last_work_day: date | None
    content_snapshot: dict | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime | None
    user_username: str | None = None
    user_nickname: str | None = None
    handover_username: str | None = None
    handover_nickname: str | None = None
