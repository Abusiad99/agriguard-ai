"""ORM models for generated agricultural reports and their share links (migration 0007)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import GUID, Base


class GeneratedReportModel(Base):
    __tablename__ = "generated_reports"
    # Same constraint as migration 0007 (so SQLite test databases enforce it too).
    __table_args__ = (UniqueConstraint("owner_id", "report_type", "subject_id", "version",
                                       name="uq_generated_reports_version"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(30), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("generated_reports.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    locale: Mapped[str] = mapped_column(String(5), nullable=False)
    crop: Mapped[str | None] = mapped_column(String(100))
    disease: Mapped[str | None] = mapped_column(String(150))
    status_summary: Mapped[str | None] = mapped_column(String(40))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    generator_version: Mapped[str] = mapped_column(String(40), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    sources_json: Mapped[list] = mapped_column(JSON, nullable=False)
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    narrative_source: Mapped[str] = mapped_column(String(20), nullable=False)
    narrative_model: Mapped[str | None] = mapped_column(String(100))
    pdf_refs_json: Mapped[dict | None] = mapped_column(JSON)
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReportShareModel(Base):
    __tablename__ = "report_shares"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("generated_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
