"""Read-only access to a report through a share link (no login). The token is checked
against a stored hash; expired or revoked links answer 404. Shared views leave out
internal record ids, and their image links expire with the share (at most an hour)."""
from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, Path
from fastapi.responses import FileResponse, Response

from app.application.reporting.service import ReportService, reference
from app.interface.api.v1.dependencies import get_report_service

router = APIRouter(prefix="/shared-reports", tags=["Reports"])

_TOKEN = Path(..., min_length=20, max_length=100, pattern=r"^[A-Za-z0-9_\-]+$")


@router.get("/{token}")
def open_shared(token: str = _TOKEN, service: ReportService = Depends(get_report_service)):
    row, share = service.open_share(token)
    out = service.to_public(row, shared=True, share_expires=share.expires_at)
    expires = share.expires_at if share.expires_at.tzinfo else share.expires_at.replace(tzinfo=timezone.utc)
    out["share_expires_at"] = expires.isoformat()
    return out


@router.get("/{token}/pdf")
def shared_pdf(token: str = _TOKEN, service: ReportService = Depends(get_report_service)):
    row, _ = service.open_share(token)
    return FileResponse(service.pdf_path(row), media_type="application/pdf", filename=f"{reference(row)}.pdf",
                        headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"})


@router.get("/{token}/map.png")
def shared_map(token: str = _TOKEN, service: ReportService = Depends(get_report_service)):
    row, _ = service.open_share(token)
    return Response(service.map_png(row), media_type="image/png", headers={"Cache-Control": "private, max-age=300"})
