"""Admin routes — FR-ADMIN-1/4 (UC-11, UC-12), BR3. See API spec §7."""
from __future__ import annotations

import csv
import io
import math
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.application.services.dashboard_admin_service import AdminService
from app.domain.entities.user import User, UserRole
from app.infrastructure.repositories.diagnosis_repository import SqlAlchemyDiagnosisRepository
from app.interface.api.v1.dependencies import get_admin_service, get_diagnosis_repository, require_roles
from app.interface.schemas.common_schemas import PaginatedUsersResponse, UpdateUserRequest, UserAdminSchema

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/users", response_model=PaginatedUsersResponse)
def list_users(
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    admin_service: AdminService = Depends(get_admin_service),
):
    page_size = min(page_size, 100)
    items, total = admin_service.list_users(current_user, role, is_active, search, page, page_size)
    return PaginatedUsersResponse(
        items=[UserAdminSchema(id=str(u.id), email=u.email, full_name=u.full_name,
                                role=u.role.value, is_active=u.is_active) for u in items],
        page=page, page_size=page_size, total=total, total_pages=max(1, math.ceil(total / page_size)),
    )


@router.patch("/users/{user_id}", response_model=UserAdminSchema)
def update_user(
    user_id: UUID,
    body: UpdateUserRequest,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    admin_service: AdminService = Depends(get_admin_service),
):
    updated = admin_service.update_user(current_user, user_id, body.role, body.is_active)
    return UserAdminSchema(id=str(updated.id), email=updated.email, full_name=updated.full_name,
                            role=updated.role.value, is_active=updated.is_active)


@router.get("/reports/export")
def export_reports(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    format: str = Query(default="csv", pattern="^(csv|json)$"),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    diagnosis_repo: SqlAlchemyDiagnosisRepository = Depends(get_diagnosis_repository),
):
    summary = diagnosis_repo.dashboard_summary(user_id=None)

    if format == "json":
        return summary

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["metric", "value"])
    writer.writerow(["total_scans", summary["total_scans"]])
    writer.writerow(["healthy_count", summary["healthy_count"]])
    writer.writerow(["diseased_count", summary["diseased_count"]])
    writer.writerow(["total_palm_scans", summary["palm_disease_stats"]["total_palm_scans"]])
    writer.writerow(["red_palm_weevil_incidents", summary["palm_disease_stats"]["red_palm_weevil_incidents"]])
    writer.writerow([])
    writer.writerow(["disease_name", "count"])
    for row in summary["most_common_diseases"]:
        writer.writerow([row["name"], row["count"]])
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=agriguard_system_report.csv"},
    )
