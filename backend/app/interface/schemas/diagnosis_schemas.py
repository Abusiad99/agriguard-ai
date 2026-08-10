from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

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
