"""Domain entities: Diagnosis and its related sub-records (pest detection, weather
snapshot, recommendation, report)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID


class SeverityLevel(str, Enum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


@dataclass
class PestDetection:
    id: Optional[UUID]
    diagnosis_id: UUID
    pest_name: str
    confidence: float
    bbox: dict  # {"x_min":.., "y_min":.., "x_max":.., "y_max":..}


@dataclass
class WeatherSnapshot:
    id: Optional[UUID]
    diagnosis_id: UUID
    temperature_c: Optional[float]
    humidity_pct: Optional[float]
    wind_speed_kmh: Optional[float]
    rain_probability_pct: Optional[float]
    uv_index: Optional[float]
    retrieved_at: datetime

    def is_fresh(self, window_hours: int) -> bool:
        return (datetime.utcnow() - self.retrieved_at).total_seconds() <= window_hours * 3600


@dataclass
class Recommendation:
    id: Optional[UUID]
    diagnosis_id: UUID
    irrigation_advice: Optional[str] = None
    spraying_advice: Optional[str] = None
    fertilizer_advice: Optional[str] = None


@dataclass
class AiAnalysis:
    """Gemini multimodal reasoning-layer output for one diagnosis (see
    infrastructure/external/gemini_client.py and
    application/services/gemini_analysis_service.py). Always optional and
    additive — a Diagnosis is fully valid and complete without one; this only
    ever supplements the CV model's diagnosis, never replaces it (see
    docs/GEMINI_INTEGRATION.md)."""

    id: Optional[UUID]
    diagnosis_id: UUID
    status: str  # "ok" | "unavailable" — never persisted for "disabled" (nothing to store)
    diagnosis_explanation: Optional[str] = None
    observed_symptoms: List[str] = field(default_factory=list)
    cv_consistency: Optional[str] = None
    confidence_assessment: Optional[str] = None
    severity_explanation: Optional[str] = None
    treatment_guidance: List[str] = field(default_factory=list)
    prevention_guidance: List[str] = field(default_factory=list)
    environmental_risk: Optional[str] = None
    urgency: Optional[str] = None
    model_name: Optional[str] = None
    message: Optional[str] = None
    generated_at: Optional[datetime] = None


@dataclass
class Report:
    id: Optional[UUID]
    diagnosis_id: UUID
    file_ref: str
    qr_code_ref: str
    generated_at: datetime


@dataclass
class Diagnosis:
    id: Optional[UUID]
    user_id: UUID
    plant_id: Optional[UUID]
    disease_id: Optional[UUID]
    confidence_score: float
    severity_level: Optional[SeverityLevel]
    affected_area_pct: Optional[float]
    healthy_area_pct: Optional[float]
    original_image_ref: str
    roi_image_ref: Optional[str] = None
    heatmap_image_ref: Optional[str] = None
    low_confidence_flag: bool = False
    unrecognized_plant: bool = False
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    supersedes_diagnosis_id: Optional[UUID] = None
    diagnosed_at: Optional[datetime] = None

    pest_detections: List[PestDetection] = field(default_factory=list)
    weather_snapshot: Optional[WeatherSnapshot] = None
    recommendation: Optional[Recommendation] = None
    report: Optional[Report] = None
    ai_analysis: Optional[AiAnalysis] = None

    def is_reviewable_low_confidence(self) -> bool:
        """BR1."""
        return self.low_confidence_flag and not self.unrecognized_plant
