from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field

from app.interface.schemas.ai_analysis_schemas import AiAnalysisSchema


class PlantSchema(BaseModel):
    name: str
    scientific_name: Optional[str] = None


class DiseaseSchema(BaseModel):
    name: str
    type: Optional[str] = None
    description: str
    symptoms: List[str] = []
    causes: List[str] = []
    transmission_method: Optional[str] = None


class TreatmentGroupSchema(BaseModel):
    instructions: Optional[str] = None
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


class QualityIssueSchema(BaseModel):
    code: str
    severity: str
    message: str
    hint: str
    metric: Optional[float] = None
    threshold: Optional[float] = None


class ImageQualitySchema(BaseModel):
    status: str  # ok | warning | rejected
    issues: List[QualityIssueSchema] = []
    metrics: Dict[str, float] = {}
    version: Optional[str] = None


class DecisionThresholdsSchema(BaseModel):
    confident: Optional[float] = None
    reject: Optional[float] = None
    plant_mass: Optional[float] = None
    source: Optional[str] = None  # validation | env_override | unvalidated_default
    temperature: Optional[float] = None
    calibrated: Optional[bool] = None


class DecisionSchema(BaseModel):
    status: Optional[str] = None
    top1_probability: Optional[float] = None
    margin: Optional[float] = None
    normalized_entropy: Optional[float] = None
    plant_identified: Optional[bool] = None
    plant_probability_mass: Optional[float] = None
    thresholds: Optional[DecisionThresholdsSchema] = None


class CandidateSchema(BaseModel):
    label: Optional[str] = None
    display_name: Optional[str] = None
    plant: Optional[str] = None
    condition: Optional[str] = None
    probability_pct: Optional[float] = None
    cause_type: Optional[str] = None
    typical_parts: List[str] = []
    symptom_patterns: List[str] = []
    regulated_in_many_regions: bool = False
    has_knowledge_base_entry: bool = False


class HintSchema(BaseModel):
    code: str
    kind: str  # consistent | also_check


class DifferentialSchema(BaseModel):
    version: Optional[str] = None
    taxonomy_version: Optional[str] = None
    model_candidates: List[CandidateSchema] = []
    also_consider: List[str] = []
    not_assessable_by_model: List[str] = []
    follow_up_questions: List[str] = []
    answers: Dict[str, Union[str, List[str]]] = {}
    hints: List[HintSchema] = []
    expert_review_recommended: bool = False
    expert_review_reasons: List[str] = []
    regulated_candidates: List[str] = []


class ExplanationSchema(BaseModel):
    method: Optional[str] = None
    available: bool = False
    reason: Optional[str] = None
    target_label: Optional[str] = None
    image_url: Optional[str] = None


class AreaMeasurementSchema(BaseModel):
    status: str
    affected_area_pct: Optional[float] = None
    healthy_area_pct: Optional[float] = None
    leaf_pixels: int = 0
    lesion_pixels: int = 0
    leaf_fraction_of_image: float = 0.0
    leaf_regions: int = 0
    lesion_regions: int = 0
    reason: Optional[str] = None


class SegmentationSchema(BaseModel):
    status: str = "unavailable"
    reason: Optional[str] = None
    method: Optional[str] = None
    model_version: Optional[str] = None
    measurement: Optional[AreaMeasurementSchema] = None
    severity: Dict[str, Optional[str]] = {}
    overlay_url: Optional[str] = None
    mask_url: Optional[str] = None


class PlantProfileRefSchema(BaseModel):
    id: str
    name: str


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
    recovery_probability: Optional[float] = None
    estimated_recovery_time: Optional[str] = None
    weather: Optional[WeatherSchema] = None
    recommendation: Optional[RecommendationSchema] = None
    report_url: Optional[str] = None
    diagnosed_at: Optional[datetime] = None
    ai_analysis: Optional[AiAnalysisSchema] = None

    # --- pipeline 2.0 reliability fields (None/empty for legacy observations) ---
    decision_status: Optional[str] = None  # confident | uncertain | inconclusive | legacy
    is_legacy: bool = False
    predicted_label: Optional[str] = None
    predicted_display_name: Optional[str] = None
    decision: Optional[DecisionSchema] = None
    image_quality: Optional[ImageQualitySchema] = None
    original_image_url: Optional[str] = None
    explanation: Optional[ExplanationSchema] = None
    segmentation: Optional[SegmentationSchema] = None
    severity_method: Optional[str] = None
    measurement_basis: Optional[str] = None  # segmentation | legacy_attention_estimate | None
    differential: Optional[DifferentialSchema] = None
    model_version: Optional[str] = None
    pipeline_version: Optional[str] = None
    plant_profile: Optional[PlantProfileRefSchema] = None
    limitations: List[str] = []


class ScanRejectedResponse(BaseModel):
    diagnosis_id: Optional[str] = None
    status: str = "rejected_image_quality"
    message: str
    quality: ImageQualitySchema


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
    decision_status: Optional[str] = None
    predicted_label: Optional[str] = None
    predicted_display_name: Optional[str] = None
    plant_profile_id: Optional[str] = None
    plant_profile_name: Optional[str] = None
    affected_area_pct: Optional[float] = None
    measurement_basis: Optional[str] = None
    image_quality_status: Optional[str] = None


class PaginatedDiagnosesResponse(BaseModel):
    items: List[DiagnosisSummarySchema]
    page: int
    page_size: int
    total: int
    total_pages: int


# ---------------- Plant profiles & observations ----------------
GROWING_ENVIRONMENT_PATTERN = "^(field|greenhouse|indoor|orchard|nursery|other)$"


class PlantProfileCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    crop_type: Optional[str] = Field(default=None, max_length=100)
    variety: Optional[str] = Field(default=None, max_length=100)
    planting_date: Optional[date] = None
    location_label: Optional[str] = Field(default=None, max_length=200)
    growing_environment: Optional[str] = Field(default=None, pattern=GROWING_ENVIRONMENT_PATTERN)
    notes: Optional[str] = Field(default=None, max_length=2000)


class PlantProfileUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    crop_type: Optional[str] = Field(default=None, max_length=100)
    variety: Optional[str] = Field(default=None, max_length=100)
    planting_date: Optional[date] = None
    location_label: Optional[str] = Field(default=None, max_length=200)
    growing_environment: Optional[str] = Field(default=None, pattern=GROWING_ENVIRONMENT_PATTERN)
    notes: Optional[str] = Field(default=None, max_length=2000)
    archived: Optional[bool] = None


class PlantProfileSchema(BaseModel):
    id: str
    name: str
    crop_type: Optional[str] = None
    variety: Optional[str] = None
    planting_date: Optional[date] = None
    location_label: Optional[str] = None
    growing_environment: Optional[str] = None
    notes: Optional[str] = None
    archived: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    observation_count: int = 0
    last_observed_at: Optional[datetime] = None
    last_decision_status: Optional[str] = None
    last_predicted_label: Optional[str] = None
    last_predicted_display_name: Optional[str] = None


class PaginatedPlantProfilesResponse(BaseModel):
    items: List[PlantProfileSchema]
    page: int
    page_size: int
    total: int
    total_pages: int


class ObservationNoteCreateRequest(BaseModel):
    note_type: str = Field(pattern="^(user_note|treatment_applied|correction|expert_feedback)$")
    body: str = Field(min_length=1, max_length=4000)


class ObservationNoteSchema(BaseModel):
    id: str
    note_type: str
    body: str
    data: dict = {}
    author_is_owner: bool = True
    created_at: Optional[datetime] = None


class FollowUpAnswersRequest(BaseModel):
    answers: Dict[str, Union[str, List[str]]]


class AssignPlantRequest(BaseModel):
    plant_profile_id: Optional[str] = None


class MeasurementPointSchema(BaseModel):
    diagnosis_id: str
    diagnosed_at: datetime
    affected_area_pct: float
    method: Optional[str] = None
    model_version: Optional[str] = None
    image_quality_status: Optional[str] = None


class TimelineEntrySchema(BaseModel):
    observation: DiagnosisSummarySchema
    notes: List[ObservationNoteSchema] = []
    treatment_summary: Optional[str] = None


class PlantTimelineResponse(BaseModel):
    plant: PlantProfileSchema
    entries: List[TimelineEntrySchema]
    page: int
    page_size: int
    total: int
    total_pages: int
    measurement_series: List[MeasurementPointSchema] = []
    measurement_series_note: Optional[str] = None
    observations_without_measurement: int = 0
