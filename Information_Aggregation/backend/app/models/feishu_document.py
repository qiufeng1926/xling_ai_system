"""飞书云文档本地镜像（元数据 + 内容快照）"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_doc_id() -> str:
    return str(uuid.uuid4())


class FeishuDocumentMirror(Base):
    __tablename__ = "feishu_document_mirrors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    feishu_token: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    feishu_type: Mapped[str] = mapped_column(String(32), nullable=False, default="docx")
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    feishu_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    feishu_modified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    snapshots: Mapped[list["FeishuDocumentSnapshot"]] = relationship(
        back_populates="mirror", cascade="all, delete-orphan"
    )


class FeishuDocumentSnapshot(Base):
    __tablename__ = "feishu_document_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    mirror_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("feishu_document_mirrors.id"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_format: Mapped[str] = mapped_column(String(32), default="plain_text")
    content_length: Mapped[int] = mapped_column(default=0)
    synced_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    mirror: Mapped[FeishuDocumentMirror] = relationship(back_populates="snapshots")


class FeishuDocumentViewGrant(Base):
    __tablename__ = "feishu_document_view_grants"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FeishuDocumentViewRequest(Base):
    __tablename__ = "feishu_document_view_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    applicant_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    applicant_nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    reviewer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    reviewer_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewer_nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class FeishuDocumentDownloadGrant(Base):
    __tablename__ = "feishu_document_download_grants"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FeishuDocumentDownloadRequest(Base):
    __tablename__ = "feishu_document_download_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    applicant_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    applicant_nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    reviewer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    reviewer_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewer_nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
