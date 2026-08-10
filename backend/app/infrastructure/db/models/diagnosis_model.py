"""SQLAlchemy models: diagnoses, pest_detections, weather_snapshots, recommendations,
reports, audit_logs. Mirrors database/01-schema.sql."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import GUID, Base


class DiagnosisModel(Base):
    __tablename__ = "diagnoses"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    plant_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("plants.id"), nullable=True)
    disease_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("diseases.id"), nullable=True)
    confidence_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    severity_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    affected_area_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    healthy_area_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    original_image_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    roi_image_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    heatmap_image_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    low_confidence_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    unrecognized_plant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    location_lat: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    location_lon: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    supersedes_diagnosis_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("diagnoses.id"), nullable=True)
    diagnosed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("UserModel", back_populates="diagnoses")
    plant = relationship("PlantModel")
    disease = relationship("DiseaseModel")
    pest_detections = relationship("PestDetectionModel", back_populates="diagnosis", cascade="all, delete-orphan")
    weather_snapshot = relationship("WeatherSnapshotModel", back_populates="diagnosis", uselist=False, cascade="all, delete-orphan")
    recommendation = relationship("RecommendationModel", back_populates="diagnosis", uselist=False, cascade="all, delete-orphan")
    report = relationship("ReportModel", back_populates="diagnosis", uselist=False, cascade="all, delete-orphan")
    ai_analysis = relationship("AiAnalysisModel", back_populates="diagnosis", uselist=False, cascade="all, delete-orphan")


class PestDetectionModel(Base):
    __tablename__ = "pest_detections"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    diagnosis_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("diagnoses.id", ondelete="CASCADE"), nullable=False, index=True)
    pest_name: Mapped[str] = mapped_column(String(150), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    bbox_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    diagnosis = relationship("DiagnosisModel", back_populates="pest_detections")


class WeatherSnapshotModel(Base):
    __tablename__ = "weather_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    diagnosis_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("diagnoses.id", ondelete="CASCADE"), nullable=False, unique=True)
    temperature_c: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    humidity_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    wind_speed_kmh: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    rain_probability_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    uv_index: Mapped[float | None] = mapped_column(Numeric(4, 1), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    diagnosis = relationship("DiagnosisModel", back_populates="weather_snapshot")


class RecommendationModel(Base):
    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    diagnosis_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("diagnoses.id", ondelete="CASCADE"), nullable=False, unique=True)
    irrigation_advice: Mapped[str | None] = mapped_column(Text, nullable=True)
    spraying_advice: Mapped[str | None] = mapped_column(Text, nullable=True)
    fertilizer_advice: Mapped[str | None] = mapped_column(Text, nullable=True)

    diagnosis = relationship("DiagnosisModel", back_populates="recommendation")


class AiAnalysisModel(Base):
    """Gemini multimodal reasoning-layer output — additive/optional, 1:1 with a
    diagnosis, same cascade-delete shape as WeatherSnapshotModel/RecommendationModel
    above. `status='unavailable'` rows are still persisted (with `message` set) so
    the history UI can show that an analysis was attempted and failed, rather than
    looking identical to a diagnosis that never had Gemini enabled at all — but a
    disabled (no GEMINI_API_KEY) scan never creates a row here at all."""
    __tablename__ = "ai_analyses"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    diagnosis_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("diagnoses.id", ondelete="CASCADE"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # "ok" | "unavailable"
    diagnosis_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_symptoms_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    cv_consistency: Mapped[str | None] = mapped_column(String(30), nullable=True)
    confidence_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    treatment_guidance_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    prevention_guidance_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    environmental_risk: Mapped[str | None] = mapped_column(Text, nullable=True)
    urgency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    diagnosis = relationship("DiagnosisModel", back_populates="ai_analysis")


class ReportModel(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    diagnosis_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("diagnoses.id", ondelete="CASCADE"), nullable=False, unique=True)
    file_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    qr_code_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    diagnosis = relationship("DiagnosisModel", back_populates="report")


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
