"""员工离职交接记录与文档"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database import Base


class UserOffboardingRecord(Base):
    __tablename__ = "user_offboarding_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    operator_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    handover_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_work_day: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    content_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    meeting_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    applicant_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    handover_confirm_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    handover_assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    documents_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    handover_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UserOffboardingDocument(Base):
    __tablename__ = "user_offboarding_documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_offboarding_records.id"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
