"""SQLAlchemy models: plant_profiles (user-owned tracked plants) and
observation_notes (append-only notes attached to a diagnosis/observation).
Mirrors migration 0003."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import GUID, Base


class PlantProfileModel(Base):
    __tablename__ = "plant_profiles"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    crop_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    variety: Mapped[str | None] = mapped_column(String(100), nullable=True)
    planting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    location_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    growing_environment: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())

    observations = relationship("DiagnosisModel", back_populates="plant_profile")


class ObservationNoteModel(Base):
    __tablename__ = "observation_notes"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    diagnosis_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("diagnoses.id", ondelete="CASCADE"), nullable=False, index=True)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    note_type: Mapped[str] = mapped_column(String(30), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    data_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    diagnosis = relationship("DiagnosisModel", back_populates="notes")
