from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    field: Optional[str] = None
    issue: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: List[ErrorDetail] = []


class ErrorResponse(BaseModel):
    error: ErrorBody
    request_id: Optional[str] = None


class PalmDiseaseStats(BaseModel):
    total_palm_scans: int
    red_palm_weevil_incidents: int


class CommonDiseaseCount(BaseModel):
    name: str
    count: int


class MonthlyTrendPoint(BaseModel):
    month: str
    scan_count: int


class DashboardResponse(BaseModel):
    total_scans: int
    healthy_count: int
    diseased_count: int
    palm_disease_stats: PalmDiseaseStats
    most_common_diseases: List[CommonDiseaseCount]
    monthly_trend: List[MonthlyTrendPoint]


class UserAdminSchema(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool


class PaginatedUsersResponse(BaseModel):
    items: List[UserAdminSchema]
    page: int
    page_size: int
    total: int
    total_pages: int


class UpdateUserRequest(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None


class DiseaseCreateRequest(BaseModel):
    plant_canonical_name: str
    name: str
    disease_type: Optional[str] = None
    description: str
    symptoms: List[str] = []
    causes: List[str] = []
    transmission_method: Optional[str] = None
    recovery_probability: Optional[float] = Field(default=None, ge=0, le=100)
    estimated_recovery_time: Optional[str] = None


class DiseaseResponseSchema(BaseModel):
    id: str
    plant_id: str
    name: str
    disease_type: Optional[str] = None
    description: str
    symptoms: List[str] = []
    causes: List[str] = []
    transmission_method: Optional[str] = None
    recovery_probability: Optional[float] = None
    estimated_recovery_time: Optional[str] = None
    version: int


class TreatmentCreateRequest(BaseModel):
    disease_id: str
    category: str
    instructions: str
    safety_notes: Optional[str] = None
    source_citation: Optional[str] = None
    authority_referral_only: bool = False


class TreatmentResponseSchema(BaseModel):
    id: str
    disease_id: str
    category: str
    instructions: str
    safety_notes: Optional[str] = None
    source_citation: Optional[str] = None
    authority_referral_only: bool
    version: int


class WeatherResponseSchema(BaseModel):
    available: bool = True
    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    rain_probability_pct: Optional[float] = None
    uv_index: Optional[float] = None
    reason: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    database: str
    cache: str
    ai_service: str
