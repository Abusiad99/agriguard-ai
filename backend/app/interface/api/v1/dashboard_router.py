"""Dashboard routes — FR-DASH-1..3 (UC-08). See API spec §5."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.application.services.dashboard_admin_service import DashboardService
from app.domain.entities.user import User
from app.interface.api.v1.dependencies import get_current_user, get_dashboard_service
from app.interface.schemas.common_schemas import (
    CommonDiseaseCount,
    DashboardResponse,
    MonthlyTrendPoint,
    PalmDiseaseStats,
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _to_schema(summary: dict) -> DashboardResponse:
    return DashboardResponse(
        total_scans=summary["total_scans"],
        healthy_count=summary["healthy_count"],
        diseased_count=summary["diseased_count"],
        palm_disease_stats=PalmDiseaseStats(**summary["palm_disease_stats"]),
        most_common_diseases=[CommonDiseaseCount(**d) for d in summary["most_common_diseases"]],
        monthly_trend=[MonthlyTrendPoint(**m) for m in summary["monthly_trend"]],
    )


@router.get("/me", response_model=DashboardResponse)
def get_my_dashboard(
    current_user: User = Depends(get_current_user),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
):
    return _to_schema(dashboard_service.get_my_dashboard(current_user.id))


@router.get("/system", response_model=DashboardResponse)
def get_system_dashboard(
    current_user: User = Depends(get_current_user),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
):
    return _to_schema(dashboard_service.get_system_dashboard(current_user))
