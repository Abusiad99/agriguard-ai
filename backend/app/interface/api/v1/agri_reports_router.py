"""Agricultural reports (docs/features/reports.md): generate, archive, view, version,
export (PDF, map image) and share. All routes need login; other users' reports answer
404. The older per-scan PDF stays at GET /api/v1/reports/{diagnosis_id}."""
from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.application.reporting.service import REPORT_TYPES, ReportService, reference, share_state
from app.domain.entities.user import User
from app.interface.api.v1.dependencies import get_current_user, get_report_service

router = APIRouter(prefix="/agri-reports", tags=["Reports"])


class ReportCreate(BaseModel):
    type: Literal["diagnosis", "plant_progress", "outbreak_area"]
    locale: Literal["en", "ar"] = "en"
    subject_id: Optional[UUID] = None
    crop: Optional[str] = Field(default=None, max_length=100)
    disease: Optional[str] = Field(default=None, max_length=150)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    horizon_days: int = Field(default=7, ge=1, le=14)


class Regenerate(BaseModel):
    locale: Optional[Literal["en", "ar"]] = None


class ShareCreate(BaseModel):
    expires_in_days: int = Field(default=7, ge=1, le=365)


def _summary(row) -> dict:
    return {"id": str(row.id), "reference": reference(row), "type": row.report_type, "version": row.version,
            "title": row.title, "locale": row.locale, "status": row.status_summary, "crop": row.crop,
            "disease": row.disease, "subject_id": str(row.subject_id), "narrative_source": row.narrative_source,
            "synthetic": bool((row.content_json or {}).get("synthetic")),
            "created_at": row.created_at.isoformat() if row.created_at else None}


def _share(s, token: Optional[str] = None) -> dict:
    out = {"id": str(s.id), "created_at": s.created_at.isoformat() if s.created_at else None,
           "expires_at": s.expires_at.isoformat(), "revoked_at": s.revoked_at.isoformat() if s.revoked_at else None,
           "access_count": s.access_count or 0, "state": share_state(s),
           "last_accessed_at": s.last_accessed_at.isoformat() if s.last_accessed_at else None}
    if token:
        out["token"] = token  # shown once; only its hash is stored
        out["path"] = f"/shared/reports/{token}"
    return out


@router.post("", status_code=status.HTTP_201_CREATED)
def create_report(body: ReportCreate, current_user: User = Depends(get_current_user),
                  service: ReportService = Depends(get_report_service)):
    row = service.generate(current_user, body.type, body.locale, body.subject_id, body.model_dump())
    return service.to_public(row)


@router.get("")
def list_reports(type: Optional[str] = Query(default=None, pattern="^(" + "|".join(REPORT_TYPES) + ")$"),
                 q: Optional[str] = Query(default=None, max_length=100), crop: Optional[str] = Query(default=None, max_length=100),
                 disease: Optional[str] = Query(default=None, max_length=150), date_from: Optional[date] = None,
                 date_to: Optional[date] = None, subject_id: Optional[UUID] = None,
                 page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
                 current_user: User = Depends(get_current_user), service: ReportService = Depends(get_report_service)):
    rows, total = service.list(current_user, report_type=type, q=q, crop=crop, disease=disease, date_from=date_from,
                               date_to=date_to, subject_id=subject_id, page=page, page_size=page_size)
    return {"items": [_summary(r) for r in rows], "page": page, "page_size": page_size, "total": total}


@router.get("/{report_id}")
def get_report(report_id: UUID, current_user: User = Depends(get_current_user),
               service: ReportService = Depends(get_report_service)):
    return service.to_public(service.get(current_user, report_id))


@router.get("/{report_id}/versions")
def list_versions(report_id: UUID, current_user: User = Depends(get_current_user),
                  service: ReportService = Depends(get_report_service)) -> List[dict]:
    return [_summary(r) for r in service.versions(current_user, report_id)]


@router.post("/{report_id}/regenerate", status_code=status.HTTP_201_CREATED)
def regenerate(report_id: UUID, body: Regenerate, current_user: User = Depends(get_current_user),
               service: ReportService = Depends(get_report_service)):
    return service.to_public(service.regenerate(current_user, report_id, body.locale))


@router.get("/{report_id}/pdf")
def download_pdf(report_id: UUID, current_user: User = Depends(get_current_user),
                 service: ReportService = Depends(get_report_service)):
    row = service.get(current_user, report_id)
    return FileResponse(service.pdf_path(row), media_type="application/pdf", filename=f"{reference(row)}.pdf",
                        headers={"Cache-Control": "private, no-store"})


@router.get("/{report_id}/map.png")
def map_image(report_id: UUID, current_user: User = Depends(get_current_user),
              service: ReportService = Depends(get_report_service)):
    row = service.get(current_user, report_id)
    return Response(service.map_png(row), media_type="image/png", headers={"Cache-Control": "private, max-age=600"})


@router.post("/{report_id}/shares", status_code=status.HTTP_201_CREATED)
def create_share(report_id: UUID, body: ShareCreate, current_user: User = Depends(get_current_user),
                 service: ReportService = Depends(get_report_service)):
    created = service.create_share(current_user, report_id, body.expires_in_days)
    return _share(created.share, created.token)


@router.get("/{report_id}/shares")
def list_shares(report_id: UUID, current_user: User = Depends(get_current_user),
                service: ReportService = Depends(get_report_service)):
    return [_share(s) for s in service.list_shares(current_user, report_id)]


@router.delete("/{report_id}/shares/{share_id}")
def revoke_share(report_id: UUID, share_id: UUID, current_user: User = Depends(get_current_user),
                 service: ReportService = Depends(get_report_service)):
    return _share(service.revoke_share(current_user, report_id, share_id))
