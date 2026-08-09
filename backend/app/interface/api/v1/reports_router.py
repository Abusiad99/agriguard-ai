"""Reports routes — FR-REPORT-2, BR5. See API spec §4."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.core.exceptions import AuthorizationError, NotFoundError
from app.domain.entities.user import User, UserRole
from app.infrastructure.repositories.diagnosis_repository import SqlAlchemyDiagnosisRepository
from app.infrastructure.storage.object_storage import LocalObjectStorage
from app.interface.api.v1.dependencies import get_current_user, get_diagnosis_repository, get_object_storage

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/{diagnosis_id}")
def download_report(
    diagnosis_id: UUID,
    current_user: User = Depends(get_current_user),
    diagnosis_repo: SqlAlchemyDiagnosisRepository = Depends(get_diagnosis_repository),
    storage: LocalObjectStorage = Depends(get_object_storage),
):
    diagnosis = diagnosis_repo.get_by_id(diagnosis_id)
    if diagnosis is None:
        raise NotFoundError("Diagnosis not found.")
    if diagnosis.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise AuthorizationError("You do not have access to this report.")
    if diagnosis.report is None:
        # BR5: a report can only be downloaded for a diagnosis that completed the
        # full pipeline; if the diagnosis exists but has no report, that pipeline
        # run never reached Step 11.
        raise NotFoundError("No completed report exists for this diagnosis.")

    file_path = storage.resolve_path(diagnosis.report.file_ref)
    if not file_path.exists():
        raise NotFoundError("The report file could not be located in storage.")

    return FileResponse(
        path=str(file_path), media_type="application/pdf",
        filename=f"agriguard_report_{diagnosis_id}.pdf",
    )
