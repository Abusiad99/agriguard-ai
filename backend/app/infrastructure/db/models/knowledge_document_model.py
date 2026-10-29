"""SQLAlchemy models: kb_documents / kb_chunks (retrieval corpus with provenance) and
assistant_usage (per-user accounting for rate/cost limits). Mirrors migration 0003."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import GUID, Base


class KbDocumentModel(Base):
    __tablename__ = "kb_documents"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    organization: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    published_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    revised_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    crops_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    diseases_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    license_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id", ondelete="SET NULL"),
                                                         nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks = relationship("KbChunkModel", back_populates="document", cascade="all, delete-orphan",
                          order_by="KbChunkModel.chunk_index")


class KbChunkModel(Base):
    __tablename__ = "kb_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_kb_chunks_doc_idx"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("kb_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str | None] = mapped_column(String(300), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    document = relationship("KbDocumentModel", back_populates="chunks")


class AssistantUsageModel(Base):
    __tablename__ = "assistant_usage"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id", ondelete="CASCADE"),
                                               nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    llm_called: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retrieved_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
