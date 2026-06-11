from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MatchRequirements(BaseModel):
    """智能匹配条件"""

    platform: str | None = None
    follower_min: int | None = Field(default=None, ge=0)
    follower_max: int | None = Field(default=None, ge=0)
    required_tag_ids: list[int] | None = Field(default=None, description="必须全部命中的标签")
    preferred_tag_ids: list[int] | None = Field(default=None, description="优先匹配的标签（加分）")
    agency_id: int | None = None
    engagement_rate_min: float | None = Field(default=None, ge=0, le=1)
    keyword: str | None = None
    must_have_contact: bool = False
    limit: int = Field(default=50, ge=1, le=200)


class MatchRequestCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    requirements: MatchRequirements


class MatchReasonDetail(BaseModel):
    dimension: str
    score: float
    max_score: float
    note: str


class MatchReasonOut(BaseModel):
    summary: str
    details: list[MatchReasonDetail] = []


class MatchInfluencerBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    platform_uid: str
    nickname: str | None
    avatar_url: str | None
    follower_count: int
    engagement_rate: float | None
    agency_name: str | None = None
    tags: list[str] = []


class MatchResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: int
    influencer_id: int
    match_score: float | None
    rank_order: int | None
    reason: MatchReasonOut | None
    is_selected: bool
    influencer: MatchInfluencerBrief | None = None


class MatchRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str | None
    requirements: dict
    status: str
    result_count: int | None
    created_at: datetime
    selected_count: int = 0


class MatchRequestDetailOut(MatchRequestOut):
    top_results: list[MatchResultOut] = []


class MatchSelectionUpdate(BaseModel):
    result_ids: list[int] = Field(..., min_length=0, max_length=200)
    selected: bool = True
