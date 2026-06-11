from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base


class MatchRequest(Base):
    __tablename__ = "match_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    requirements: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    result_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    results: Mapped[list["MatchResult"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class MatchResult(Base):
    __tablename__ = "match_results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("match_requests.id", ondelete="CASCADE"), nullable=False
    )
    influencer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("influencers.id"), nullable=False)
    match_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    rank_order: Mapped[int | None] = mapped_column(Integer)
    reason: Mapped[dict | None] = mapped_column(JSON)
    is_selected: Mapped[int] = mapped_column(default=0)

    request: Mapped[MatchRequest] = relationship(back_populates="results")
    influencer: Mapped["Influencer"] = relationship()
