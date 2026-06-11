from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AgencyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    platform: str | None = Field(default=None, max_length=20)
    contact_person: str | None = None
    contact_phone: str | None = None
    contact_wechat: str | None = None
    policy_notes: str | None = None
    cooperation_terms: dict | None = None


class AgencyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    platform: str | None = None
    contact_person: str | None = None
    contact_phone: str | None = None
    contact_wechat: str | None = None
    policy_notes: str | None = None
    cooperation_terms: dict | None = None


class AgencyBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    platform: str | None = None


class AgencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    platform: str | None
    contact_person: str | None
    contact_phone: str | None
    contact_wechat: str | None
    policy_notes: str | None
    cooperation_terms: dict | None
    created_at: datetime
    updated_at: datetime
    influencer_count: int = 0
    avg_follower_count: int = 0


class AgencyDetailOut(AgencyOut):
    total_followers: int = 0
