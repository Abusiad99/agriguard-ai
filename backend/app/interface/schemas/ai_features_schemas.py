"""Request/response schemas for the AI features: model registry, disease localization,
plant recovery monitoring and outbreak risk."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

TreatmentStage = Literal["before_treatment", "during_treatment", "after_treatment", "unknown"]
TreatmentCategory = Literal["organic", "chemical", "biological", "cultural", "other"]
RecoveryStatus = Literal["improving", "stable", "worsening", "inconclusive", "insufficient_data"]


# ------------------------------------------------------------------ model registry
class ModelCardSchema(BaseModel):
    task: str
    readiness: str
    message: str
    name: Optional[str] = None
    version: Optional[str] = None
    architecture: Optional[str] = None
    dataset_version: Optional[str] = None
    training_status: Optional[str] = None
    trained_at: Optional[str] = None
    classes: List[str] = []
    metrics: Dict[str, Any] = {}


# ------------------------------------------------------------------ localization
class SegmentationClassSchema(BaseModel):
    id: int
    name: str
    kind: str
    color: List[int]


class SegmentationRegionSchema(BaseModel):
    label: str
    class_id: int
    pixels: int
    bbox: Dict[str, int]
    mean_confidence: Optional[float] = None


class SegmentationArtifactsSchema(BaseModel):
    mask: str
    overlay: str
    contours: str


class SegmentationSchema(BaseModel):
    status: str  # ok | failed | not_trained | dataset_unavailable | unavailable | ...
    message: Optional[str] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    mask_width: Optional[int] = None
    mask_height: Optional[int] = None
    affected_pixels: Optional[int] = None
    plant_pixels: Optional[int] = None
    affected_area_pct: Optional[float] = None
    area_basis: Optional[str] = None
    area_unavailable_reason: Optional[str] = None
    mean_confidence: Optional[float] = None
    mean_uncertainty: Optional[float] = None
    classes: List[SegmentationClassSchema] = []
    regions: List[SegmentationRegionSchema] = []
    artifacts: Optional[SegmentationArtifactsSchema] = None
    created_at: Optional[datetime] = None


class TrackedPlantRefSchema(BaseModel):
    id: str
    name: str


# ------------------------------------------------------------------ recovery
class _Location(BaseModel):
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _both_or_neither(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be given together")
        return self


class TrackedPlantCreate(_Location):
    name: str = Field(min_length=1, max_length=120)
    crop: Optional[str] = Field(default=None, max_length=100)
    species: Optional[str] = Field(default=None, max_length=150)
    notes: Optional[str] = Field(default=None, max_length=4000)
    initial_diagnosis_id: Optional[str] = None


class TrackedPlantUpdate(_Location):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    crop: Optional[str] = Field(default=None, max_length=100)
    species: Optional[str] = Field(default=None, max_length=150)
    notes: Optional[str] = Field(default=None, max_length=4000)
    status: Optional[Literal["active", "archived"]] = None
    clear_location: bool = False


class TrackedPlantSchema(BaseModel):
    id: str
    name: str
    crop: Optional[str] = None
    species: Optional[str] = None
    notes: Optional[str] = None
    status: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    initial_diagnosis_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    scan_count: int = 0
    last_scan_at: Optional[datetime] = None
    latest_status: Optional[RecoveryStatus] = None
    next_reminder_on: Optional[date] = None


class PaginatedTrackedPlants(BaseModel):
    items: List[TrackedPlantSchema]
    page: int
    page_size: int
    total: int


class ScanLinkCreate(BaseModel):
    diagnosis_id: str
    treatment_stage: TreatmentStage = "unknown"
    notes: Optional[str] = Field(default=None, max_length=2000)


class PlantScanSchema(BaseModel):
    diagnosis_id: str
    diagnosed_at: Optional[datetime] = None
    treatment_stage: str
    notes: Optional[str] = None
    predicted_condition: Optional[str] = None
    is_healthy: Optional[bool] = None
    confidence_score: Optional[float] = None
    low_confidence_flag: bool = False
    image_url: Optional[str] = None
    image_quality: Optional[Dict[str, Any]] = None
    segmentation_status: Optional[str] = None
    affected_area_pct: Optional[float] = None
    segmentation_model: Optional[str] = None


class AssessmentSchema(BaseModel):
    id: Optional[str] = None
    status: RecoveryStatus
    method_version: str
    baseline_diagnosis_id: Optional[str] = None
    latest_diagnosis_id: Optional[str] = None
    indicators: List[Dict[str, Any]] = []
    limitations: List[str] = []
    area_series: List[Dict[str, Any]] = []
    summary: Optional[str] = None
    created_at: Optional[datetime] = None


class TreatmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: TreatmentCategory
    applied_on: date
    application_notes: Optional[str] = Field(default=None, max_length=4000)
    dosage_text: Optional[str] = Field(default=None, max_length=500)
    documentation_ref: Optional[str] = Field(default=None, max_length=500)
    follow_up_on: Optional[date] = None
    user_notes: Optional[str] = Field(default=None, max_length=4000)


class TreatmentRecordSchema(BaseModel):
    id: str
    name: str
    category: str
    applied_on: date
    application_notes: Optional[str] = None
    dosage_text: Optional[str] = None
    documentation_ref: Optional[str] = None
    follow_up_on: Optional[date] = None
    user_notes: Optional[str] = None
    created_at: Optional[datetime] = None
    source: Literal["user_recorded"] = "user_recorded"


class ReminderCreate(BaseModel):
    kind: Literal["next_scan", "treatment_follow_up"]
    due_on: date
    note: Optional[str] = Field(default=None, max_length=500)
    treatment_record_id: Optional[str] = None


class ReminderUpdate(BaseModel):
    status: Literal["pending", "completed", "dismissed"]


class ReminderSchema(BaseModel):
    id: str
    tracked_plant_id: str
    plant_name: Optional[str] = None
    kind: str
    due_on: date
    status: str
    state: str  # pending | overdue | completed | dismissed
    note: Optional[str] = None
    treatment_record_id: Optional[str] = None
    completed_at: Optional[datetime] = None


class PaginatedReminders(BaseModel):
    items: List[ReminderSchema]
    page: int
    page_size: int
    total: int


class TimelineEventSchema(BaseModel):
    id: str
    event_type: str
    occurred_at: datetime
    diagnosis_id: Optional[str] = None
    treatment_record_id: Optional[str] = None
    reminder_id: Optional[str] = None
    assessment_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class PaginatedTimeline(BaseModel):
    items: List[TimelineEventSchema]
    page: int
    page_size: int
    total: int


class TrackedPlantDetailSchema(BaseModel):
    plant: TrackedPlantSchema
    scans: List[PlantScanSchema]
    assessment: AssessmentSchema
    treatments: List[TreatmentRecordSchema]
    reminders: List[ReminderSchema]


class CompareResponse(BaseModel):
    first: PlantScanSchema
    second: PlantScanSchema
    checks: Dict[str, Any]
    area_change: Optional[Dict[str, Any]] = None
    limitations: List[str]


# ------------------------------------------------------------------ outbreak
class PredictionRequest(_Location):
    crop: str = Field(min_length=1, max_length=100)
    disease: str = Field(min_length=1, max_length=150)
    horizon_days: int = Field(default=7, ge=1, le=14)
    area_id: Optional[str] = None

    @model_validator(mode="after")
    def _area_or_location(self):
        if not self.area_id and self.latitude is None:
            raise ValueError("give either area_id or latitude/longitude")
        return self
