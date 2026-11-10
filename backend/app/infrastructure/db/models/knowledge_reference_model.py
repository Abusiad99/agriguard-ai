"""ORM models for knowledge-base references and their claims (migration 0008)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import GUID, Base


class KnowledgeReferenceModel(Base):
    __tablename__ = "knowledge_references"
    __table_args__ = (
        UniqueConstraint("url", name="uq_knowledge_references_url"),
        CheckConstraint("source_type IN ('agricultural_authority', 'university_extension', 'research_institute', "
                        "'peer_reviewed', 'international_organization', 'educational_resource', 'other')",
                        name="ck_knowledge_references_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[str | None] = mapped_column(String(500))
    organization: Mapped[str | None] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    doi: Mapped[str | None] = mapped_column(String(200))
    publication_date: Mapped[str | None] = mapped_column(String(60))
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    notes: Mapped[str | None] = mapped_column(Text)
    verified_on: Mapped[date | None] = mapped_column(Date)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    claims = relationship("KnowledgeReferenceClaimModel", back_populates="reference", cascade="all, delete-orphan",
                          order_by="KnowledgeReferenceClaimModel.created_at")


class KnowledgeReferenceClaimModel(Base):
    __tablename__ = "knowledge_reference_claims"
    __table_args__ = (
        CheckConstraint("subject_type IN ('disease', 'treatment', 'rule', 'guidance', 'method')",
                        name="ck_reference_claims_type"),
        CheckConstraint("subject_key IS NOT NULL OR subject_id IS NOT NULL", name="ck_reference_claims_subject"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    reference_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("knowledge_references.id", ondelete="CASCADE"),
                                                    nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(20), nullable=False)
    subject_key: Mapped[str | None] = mapped_column(String(200))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    reference = relationship("KnowledgeReferenceModel", back_populates="claims")
