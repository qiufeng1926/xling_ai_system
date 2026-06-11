from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base


class CollectionTask(Base):
    __tablename__ = "collection_tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    keyword: Mapped[str] = mapped_column(String(200), nullable=False)
    filters: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    result_count: Mapped[int] = mapped_column(default=0)
    approved_count: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(default=0)
    error_category: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    items: Mapped[list["CollectedInfluencer"]] = relationship(back_populates="task")


class CollectedInfluencer(Base):
    __tablename__ = "collected_influencers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("collection_tasks.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    platform_uid: Mapped[str] = mapped_column(String(100), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(200))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    profile_url: Mapped[str | None] = mapped_column(Text)
    follower_count: Mapped[int] = mapped_column(BigInteger, default=0)
    engagement_rate: Mapped[float | None] = mapped_column(Numeric(5, 4))
    avg_views: Mapped[int | None] = mapped_column(BigInteger)
    source: Mapped[str | None] = mapped_column(String(50))
    matched_tags: Mapped[list | None] = mapped_column(JSON)
    match_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    extra_data: Mapped[dict | None] = mapped_column(JSON)
    review_status: Mapped[str] = mapped_column(String(20), default="pending")
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    influencer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("influencers.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    task: Mapped[CollectionTask] = relationship(back_populates="items")
