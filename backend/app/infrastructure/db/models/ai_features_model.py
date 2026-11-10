"""ORM models for the three AI features (migrations 0004-0006):
disease localization, plant recovery monitoring and outbreak prediction."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (JSON, BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import GUID, Base


# --------------------------------------------------------------------------- localization
class DiagnosisSegmentationModel(Base):
    __tablename__ = "diagnosis_segmentations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    diagnosis_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("diagnoses.id", ondelete="CASCADE"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(100))
    model_version: Mapped[str | None] = mapped_column(String(150))
    image_width: Mapped[int | None] = mapped_column(Integer)
    image_height: Mapped[int | None] = mapped_column(Integer)
    mask_width: Mapped[int | None] = mapped_column(Integer)
    mask_height: Mapped[int | None] = mapped_column(Integer)
    affected_pixels: Mapped[int | None] = mapped_column(BigInteger)
    plant_pixels: Mapped[int | None] = mapped_column(BigInteger)
    affected_area_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    area_basis: Mapped[str | None] = mapped_column(String(30))
    area_unavailable_reason: Mapped[str | None] = mapped_column(String(60))
    class_pixels_json: Mapped[dict | None] = mapped_column(JSON)
    regions_json: Mapped[list | None] = mapped_column(JSON)
    classes_json: Mapped[list | None] = mapped_column(JSON)
    mean_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    mean_uncertainty: Mapped[float | None] = mapped_column(Numeric(5, 4))
    inference_ms: Mapped[int | None] = mapped_column(Integer)
    artifact_dir: Mapped[str | None] = mapped_column(String(500))
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --------------------------------------------------------------------------- recovery
class TrackedPlantModel(Base):
    __tablename__ = "tracked_plants"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    crop: Mapped[str | None] = mapped_column(String(100))
    species: Mapped[str | None] = mapped_column(String(150))
    location_lat: Mapped[float | None] = mapped_column(Numeric(9, 6))
    location_lon: Mapped[float | None] = mapped_column(Numeric(9, 6))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    initial_diagnosis_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("diagnoses.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TrackedPlantScanModel(Base):
    __tablename__ = "tracked_plant_scans"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tracked_plant_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("tracked_plants.id", ondelete="CASCADE"), nullable=False, index=True)
    diagnosis_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("diagnoses.id", ondelete="CASCADE"), nullable=False, unique=True)
    treatment_stage: Mapped[str] = mapped_column(String(30), nullable=False, default="unknown")
    notes: Mapped[str | None] = mapped_column(Text)
    associated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TreatmentRecordModel(Base):
    __tablename__ = "treatment_records"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tracked_plant_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("tracked_plants.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    applied_on: Mapped[date] = mapped_column(Date, nullable=False)
    application_notes: Mapped[str | None] = mapped_column(Text)
    dosage_text: Mapped[str | None] = mapped_column(String(500))
    documentation_ref: Mapped[str | None] = mapped_column(String(500))
    follow_up_on: Mapped[date | None] = mapped_column(Date)
    user_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FollowUpReminderModel(Base):
    __tablename__ = "follow_up_reminders"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tracked_plant_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("tracked_plants.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    treatment_record_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("treatment_records.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(String(500))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecoveryAssessmentModel(Base):
    __tablename__ = "recovery_assessments"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tracked_plant_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("tracked_plants.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    method_version: Mapped[str] = mapped_column(String(30), nullable=False)
    baseline_diagnosis_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("diagnoses.id", ondelete="SET NULL"))
    latest_diagnosis_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("diagnoses.id", ondelete="SET NULL"))
    indicators_json: Mapped[list | None] = mapped_column(JSON)
    limitations_json: Mapped[list | None] = mapped_column(JSON)
    area_series_json: Mapped[list | None] = mapped_column(JSON)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlantTimelineEventModel(Base):
    __tablename__ = "plant_timeline_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tracked_plant_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("tracked_plants.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    diagnosis_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("diagnoses.id", ondelete="SET NULL"))
    treatment_record_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("treatment_records.id", ondelete="SET NULL"))
    reminder_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("follow_up_reminders.id", ondelete="SET NULL"))
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("recovery_assessments.id", ondelete="SET NULL"))
    details_json: Mapped[dict | None] = mapped_column(JSON)


# --------------------------------------------------------------------------- outbreak
class GeoAreaModel(Base):
    __tablename__ = "geo_areas"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    grid_key: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    resolution_deg: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    lat_index: Mapped[int] = mapped_column(Integer, nullable=False)
    lon_index: Mapped[int] = mapped_column(Integer, nullable=False)
    south: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    west: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    north: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    east: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    center_lat: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    center_lon: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    name: Mapped[str | None] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DiseaseObservationModel(Base):
    __tablename__ = "disease_observations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    area_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("geo_areas.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    diagnosis_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("diagnoses.id", ondelete="CASCADE"), unique=True)
    dataset_version: Mapped[str | None] = mapped_column(String(40))
    crop: Mapped[str] = mapped_column(String(100), nullable=False)
    disease: Mapped[str] = mapped_column(String(150), nullable=False)
    is_positive: Mapped[bool] = mapped_column(Boolean, nullable=False)
    inspected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    positive_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observed_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WeatherObservationModel(Base):
    __tablename__ = "weather_observations"
    __table_args__ = (UniqueConstraint("area_id", "day", "kind", name="uq_weather_observations"),)  # as in migration 0006

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    area_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("geo_areas.id", ondelete="CASCADE"), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    temperature_mean_c: Mapped[float | None] = mapped_column(Numeric(5, 2))
    temperature_min_c: Mapped[float | None] = mapped_column(Numeric(5, 2))
    temperature_max_c: Mapped[float | None] = mapped_column(Numeric(5, 2))
    relative_humidity_mean_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    rh_hours_ge_90: Mapped[float | None] = mapped_column(Numeric(4, 1))
    precipitation_mm: Mapped[float | None] = mapped_column(Numeric(7, 2))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutbreakPredictionModel(Base):
    __tablename__ = "outbreak_predictions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    area_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("geo_areas.id", ondelete="CASCADE"), nullable=False, index=True)
    crop: Mapped[str] = mapped_column(String(100), nullable=False)
    disease: Mapped[str] = mapped_column(String(150), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_start: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[float | None] = mapped_column(Numeric(6, 4))
    score_kind: Mapped[str | None] = mapped_column(String(30))
    confidence_level: Mapped[str | None] = mapped_column(String(10))
    data_completeness: Mapped[float | None] = mapped_column(Numeric(4, 3))
    model_name: Mapped[str | None] = mapped_column(String(100))
    model_version: Mapped[str | None] = mapped_column(String(150))
    factors_json: Mapped[list | None] = mapped_column(JSON)
    features_json: Mapped[dict | None] = mapped_column(JSON)
    suitability_json: Mapped[list | None] = mapped_column(JSON)
    limitations_json: Mapped[list | None] = mapped_column(JSON)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
