from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from app.interface.schemas.ai_analysis_schemas import AiAnalysisSchema
from app.interface.schemas.ai_features_schemas import SegmentationSchema, TrackedPlantRefSchema


class PlantSchema(BaseModel):
    name: str
    scientific_name: Optional[str] = None


class DiseaseSchema(BaseModel):
    name: str
    type: Optional[str] = None
    description: str
    # "not_listed": the model predicted a condition that has no knowledge-base entry yet.
    # `description` then holds a fixed English notice; clients show their own translation.
    # It says nothing about whether the condition is real, only that AgriGuard has no entry.
    knowledge_base_status: Literal["listed", "not_listed"] = "listed"
    symptoms: List[str] = []
    causes: List[str] = []
    transmission_method: Optional[str] = None


class TreatmentGroupSchema(BaseModel):
    instructions: Optional[str] = None
    # True when the stored instructions may not be shown (BR6: no cited dosage source, or
    # referral-only). `instructions` then holds a fixed English referral to the local
    # agricultural authority; clients show their own translation.
    instructions_withheld: bool = False
    safety_notes: Optional[str] = None
    source_citation: Optional[str] = None


class TreatmentSchema(BaseModel):
    organic: Optional[TreatmentGroupSchema] = None
    chemical: Optional[TreatmentGroupSchema] = None
    biological: Optional[TreatmentGroupSchema] = None


class PestSchema(BaseModel):
    name: str
    confidence: float
    bbox: dict


class WeatherSchema(BaseModel):
    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    rain_probability_pct: Optional[float] = None
    uv_index: Optional[float] = None


class RecommendationSchema(BaseModel):
    irrigation_advice: Optional[str] = None
    spraying_advice: Optional[str] = None
    fertilizer_advice: Optional[str] = None


class WeatherGuidanceSchema(BaseModel):
    """Spraying conditions from measured weather and verified sources
    (app/application/reporting/weather_guidance.py), in English and Arabic."""
    verdict: str
    observed_at: Optional[str] = None
    limits: Dict[str, float] = {}
    measurements: Dict[str, Any] = {}
    summary: Dict[str, str] = {}
    items: List[Dict[str, Any]] = []
    references: List[Dict[str, Any]] = []
    rules_version: Optional[str] = None


class DiagnosisResponse(BaseModel):
    diagnosis_id: str
    status: str
    plant: Optional[PlantSchema] = None
    disease: Optional[DiseaseSchema] = None
    confidence_score: float
    severity_level: Optional[str] = None
    affected_area_pct: Optional[float] = None
    healthy_area_pct: Optional[float] = None
    roi_image_url: Optional[str] = None
    heatmap_image_url: Optional[str] = None
    low_confidence_flag: bool = False
    pests_detected: List[PestSchema] = []
    treatment: Optional[TreatmentSchema] = None
    prevention_advice: List[str] = []
    # Stable codes for prevention_advice, same order (general practice, not disease-specific).
    prevention_advice_codes: List[str] = []
    recovery_probability: Optional[float] = None
    estimated_recovery_time: Optional[str] = None
    weather: Optional[WeatherSchema] = None
    recommendation: Optional[RecommendationSchema] = None
    weather_guidance: Optional[WeatherGuidanceSchema] = None
    report_url: Optional[str] = None
    diagnosed_at: Optional[datetime] = None
    ai_analysis: Optional[AiAnalysisSchema] = None
    # How severity_level / affected_area_pct above were derived. "explainability_heatmap"
    # = thresholded Grad-CAM attention map: an estimate, not a measured lesion area.
    severity_method: Optional[str] = None
    # Disease localization by the separate segmentation model (null for scans made
    # before the feature existed); `status` says why when no model ran.
    segmentation: Optional[SegmentationSchema] = None
    image_quality: Optional[Dict[str, Any]] = None
    # The owner's tracked plant for this scan; only returned to the owner.
    tracked_plant: Optional[TrackedPlantRefSchema] = None
    # False when an admin views someone else's diagnosis (owner-only actions such as
    # "track this plant" are hidden); null where the viewer is not known.
    viewer_is_owner: Optional[bool] = None


class UnrecognizedPlantResponse(BaseModel):
    diagnosis_id: Optional[str] = None
    status: str = "unrecognized_plant"
    message: str


class DiagnosisSummarySchema(BaseModel):
    id: str
    plant: Optional[str] = None
    disease: Optional[str] = None
    severity_level: Optional[str] = None
    confidence_score: float
    thumbnail_url: Optional[str] = None
    diagnosed_at: Optional[datetime] = None


class PaginatedDiagnosesResponse(BaseModel):
    items: List[DiagnosisSummarySchema]
    page: int
    page_size: int
    total: int
    total_pages: int
