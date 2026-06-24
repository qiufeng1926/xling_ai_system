from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants.permissions import ALL_REQUEST_TYPES


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    nickname: str | None
    role: str
    status: int
    view_library: bool = False
    view_all_meetings: bool = False
    view_root_meetings: bool = False
    view_all_root_meetings: bool = False
    download_meetings: bool = False
    approve_meeting_download: bool = False
    approve_meeting_view: bool = False
    permissions: dict[str, bool] = Field(default_factory=dict)
    created_at: datetime
    feishu_bound: bool = False
    feishu_name: str | None = None
    account_status: str = "active"
    offboarded_at: datetime | None = None


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="用户名至少 3 个字符")
    password: str = Field(..., min_length=8, max_length=128, description="密码至少 8 位")
    nickname: str | None = None
    role: str = Field(default="user", description="admin/user")


class UserUpdate(BaseModel):
    nickname: str | None = None
    role: str | None = None
    status: int | None = None
    view_library: bool | None = None
    view_all_meetings: bool | None = None
    view_root_meetings: bool | None = None
    view_all_root_meetings: bool | None = None
    download_meetings: bool | None = None
    approve_meeting_download: bool | None = None
    approve_meeting_view: bool | None = None
    password: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, password: str | None) -> str | None:
        if password is None or password == "":
            return None
        if len(password) < 8:
            raise ValueError("密码至少 8 位")
        return password


class ViewAccessRequestCreate(BaseModel):
    request_type: str = Field(default="view_library")
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("request_type")
    @classmethod
    def validate_request_type(cls, value: str) -> str:
        if value not in ALL_REQUEST_TYPES:
            raise ValueError("无效的申请类型")
        return value


class ViewAccessRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    request_type: str = "view_library"
    status: str
    reason: str | None
    reviewer_id: int | None
    review_note: str | None
    created_at: datetime
    reviewed_at: datetime | None
    username: str | None = None
    nickname: str | None = None
    reviewer_username: str | None = None
    reviewer_nickname: str | None = None
    request_type_label: str | None = None


class AccessReviewAction(BaseModel):
    approve: bool
    review_note: str | None = None


class SystemSettingOut(BaseModel):
    block_upper_role_tasks: bool = True
