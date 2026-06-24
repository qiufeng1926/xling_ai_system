from datetime import datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base
from app.models.collection import CollectedInfluencer, CollectionTask
from app.models.match import MatchRequest, MatchResult

from app.models.permission import SystemSetting, ViewAccessRequest

from app.models.offboarding import UserOffboardingRecord

__all__ = [
    "User",
    "Agency",
    "Influencer",
    "InfluencerProfile",
    "Tag",
    "InfluencerTag",
    "CollectionTask",
    "CollectedInfluencer",
    "MatchRequest",
    "MatchResult",
    "ViewAccessRequest",
    "SystemSetting",
    "UserOffboardingRecord",
]


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="user")
    view_library: Mapped[int] = mapped_column(default=0)
    # 会议 AI 模块权限（xling 平台统一管理）
    view_all_meetings: Mapped[int] = mapped_column(default=0)
    view_root_meetings: Mapped[int] = mapped_column(default=0)
    view_all_root_meetings: Mapped[int] = mapped_column(default=0)
    download_meetings: Mapped[int] = mapped_column(default=0)
    approve_meeting_download: Mapped[int] = mapped_column(default=0)
    approve_meeting_view: Mapped[int] = mapped_column(default=0)
    status: Mapped[int] = mapped_column(default=1)
    account_status: Mapped[str] = mapped_column(String(20), default="active")
    offboarded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    feishu_open_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    feishu_union_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    feishu_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    feishu_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    feishu_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    feishu_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    feishu_oauth_scope: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Agency(Base):
    __tablename__ = "agencies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    platform: Mapped[str | None] = mapped_column(String(20))
    contact_person: Mapped[str | None] = mapped_column(String(100))
    contact_phone: Mapped[str | None] = mapped_column(String(50))
    contact_wechat: Mapped[str | None] = mapped_column(String(100))
    policy_notes: Mapped[str | None] = mapped_column(Text)
    cooperation_terms: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    influencers: Mapped[list["Influencer"]] = relationship(back_populates="agency")


class Influencer(Base):
    __tablename__ = "influencers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    platform_uid: Mapped[str] = mapped_column(String(100), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(200))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    profile_url: Mapped[str | None] = mapped_column(Text)
    agency_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("agencies.id"))
    follower_count: Mapped[int] = mapped_column(BigInteger, default=0)
    engagement_rate: Mapped[float | None] = mapped_column(Numeric(5, 4))
    source: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[int] = mapped_column(default=1)
    extra_data: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    agency: Mapped[Agency | None] = relationship(back_populates="influencers")
    profile: Mapped["InfluencerProfile | None"] = relationship(
        back_populates="influencer", uselist=False
    )
    tags: Mapped[list["InfluencerTag"]] = relationship(back_populates="influencer")


class InfluencerProfile(Base):
    __tablename__ = "influencer_profiles"

    influencer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("influencers.id"), primary_key=True
    )
    contact_info: Mapped[dict | None] = mapped_column(JSON)
    shooting_style: Mapped[list | None] = mapped_column(JSON)
    persona_traits: Mapped[list | None] = mapped_column(JSON)
    cooperation_policy: Mapped[str | None] = mapped_column(Text)
    internal_notes: Mapped[str | None] = mapped_column(Text)
    last_contact_date: Mapped[datetime | None] = mapped_column(Date)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    influencer: Mapped[Influencer] = relationship(back_populates="profile")


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("tags.id"))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50))
    level: Mapped[int] = mapped_column(default=1)

    influencer_tags: Mapped[list["InfluencerTag"]] = relationship(back_populates="tag")


class InfluencerTag(Base):
    __tablename__ = "influencer_tags"

    influencer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("influencers.id"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tags.id"), primary_key=True)
    source: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))

    influencer: Mapped[Influencer] = relationship(back_populates="tags")
    tag: Mapped[Tag] = relationship(back_populates="influencer_tags")
