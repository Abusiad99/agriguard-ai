"""SQLAlchemy models: plants, diseases, treatments. Mirrors database/01-schema.sql."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import GUID, Base


class PlantModel(Base):
    __tablename__ = "plants"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    canonical_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    scientific_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    synonyms_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    diseases = relationship("DiseaseModel", back_populates="plant")


class DiseaseModel(Base):
    __tablename__ = "diseases"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    plant_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("plants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    disease_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    symptoms_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    causes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    transmission_method: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recovery_probability: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    estimated_recovery_time: Mapped[str | None] = mapped_column(String(100), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    plant = relationship("PlantModel", back_populates="diseases")
    treatments = relationship("TreatmentModel", back_populates="disease")


class TreatmentModel(Base):
    __tablename__ = "treatments"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    disease_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("diseases.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    safety_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_citation: Mapped[str | None] = mapped_column(String(500), nullable=True)
    authority_referral_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    disease = relationship("DiseaseModel", back_populates="treatments")
