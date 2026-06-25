from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class OffboardingApplyRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    last_work_day: date | None = None


class OffboardingAssignHandoverRequest(BaseModel):
    handover_user_id: int = Field(..., ge=1)


class OffboardingConfirmHandoverRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class OffboardingDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_size: int
    uploaded_at: datetime


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
    applicant_note: str | None = None
    handover_confirm_note: str | None = None
    handover_assigned_at: datetime | None = None
    documents_submitted_at: datetime | None = None
    handover_confirmed_at: datetime | None = None
    documents: list[OffboardingDocumentOut] = Field(default_factory=list)
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime | None
    user_username: str | None = None
    user_nickname: str | None = None
    handover_username: str | None = None
    handover_nickname: str | None = None
