from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")


class ResponseBase(BaseModel, Generic[T]):
    code: int = 0
    message: str = "success"
    data: T | None = None


class PageParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserLogin(BaseModel):
    username: str
    password: str


class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="用户名至少 3 个字符")
    nickname: str = Field(..., min_length=1, max_length=100, description="昵称")
    password: str = Field(..., min_length=8, max_length=128, description="密码至少 8 位")
    password_confirm: str = Field(..., min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self) -> "UserRegister":
        if self.password != self.password_confirm:
            raise ValueError("两次输入的密码不一致")
        return self


class FeishuBindRequest(BaseModel):
    user_id: int = Field(..., ge=1)
    open_id: str = Field(..., min_length=8, max_length=64)
    union_id: str | None = Field(default=None, max_length=64)
    name: str = Field(..., min_length=1, max_length=100)
    avatar_url: str | None = None
    email: str | None = None
    mobile: str | None = None
    tenant_key: str | None = None
    access_token: str = Field(..., min_length=8)
    refresh_token: str | None = None
    token_expires_at: datetime | None = None
    oauth_scope: str | None = Field(default=None, max_length=512)


class FeishuBindStatus(BaseModel):
    bound: bool
    feishu_name: str | None = None
    token_valid: bool = False
    docs_authorized: bool = False
    minutes_authorized: bool = False
    oauth_scope: str | None = None
    portal_username: str | None = None
    portal_nickname: str | None = None


class FeishuTokenBundleRequest(BaseModel):
    user_id: int = Field(..., ge=1)


class FeishuTokenBundleUpdateRequest(BaseModel):
    user_id: int = Field(..., ge=1)
    access_token: str = Field(..., min_length=8)
    refresh_token: str | None = None
    token_expires_at: datetime | None = None


class FeishuTokenBundle(BaseModel):
    open_id: str
    union_id: str | None = None
    access_token: str
    refresh_token: str | None = None
    token_expires_at: datetime | None = None


class UserInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    nickname: str | None
    role: str
    view_library: bool = False
    permissions: dict[str, bool] = Field(default_factory=dict)


class TagBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str | None


class InfluencerProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    contact_info: dict | None = None
    shooting_style: list | None = None
    persona_traits: list | None = None
    cooperation_policy: str | None = None
    internal_notes: str | None = None
    last_contact_date: datetime | None = None


class InfluencerBase(BaseModel):
    platform: str = Field(..., description="douyin/xiaohongshu/kuaishou/wechat")
    platform_uid: str
    nickname: str | None = None
    avatar_url: str | None = None
    profile_url: str | None = None
    agency_id: int | None = None
    follower_count: int = 0
    engagement_rate: float | None = None
    source: str | None = None
    extra_data: dict | None = None


class InfluencerCreate(InfluencerBase):
    pass


class InfluencerUpdate(BaseModel):
    nickname: str | None = None
    avatar_url: str | None = None
    profile_url: str | None = None
    agency_id: int | None = None
    follower_count: int | None = None
    engagement_rate: float | None = None
    source: str | None = None
    status: int | None = None
    extra_data: dict | None = None
    profile: InfluencerProfileOut | None = None


class InfluencerOut(InfluencerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: int
    created_at: datetime
    updated_at: datetime
    tags: list[TagBrief] = []
    profile: InfluencerProfileOut | None = None
    agency_name: str | None = None


class InfluencerFilter(BaseModel):
    platform: str | None = None
    source: str | None = None
    keyword: str | None = None
    follower_min: int | None = None
    follower_max: int | None = None
    tag_ids: list[int] | None = None
    agency_id: int | None = None
    status: int | None = 1


class ImportResult(BaseModel):
    total: int
    success: int
    failed: int
    errors: list[str] = []
