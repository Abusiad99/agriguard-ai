"""
Dependency Injection (requirement #9). Every route handler receives its
repositories/services through FastAPI's `Depends()` mechanism, constructed here from
the current request-scoped DB session — nothing is instantiated at import time, and
nothing is a global singleton except the stateless security/AI helper classes.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.application.services.auth_service import AuthService
from app.application.services.dashboard_admin_service import AdminService, DashboardService
from app.application.services.gemini_analysis_service import GeminiAnalysisService
from app.application.services.knowledge_base_service import KnowledgeBaseService
from app.application.services.outbreak_service import OutbreakService
from app.application.services.recovery_service import RecoveryService
from app.application.services.scan_service import ScanOrchestrator
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, AuthorizationError, TokenExpiredOrInvalidError
from app.domain.entities.user import User, UserRole
from app.infrastructure.db.session import get_db
from app.infrastructure.external.ai_pipeline_client import AiPipelineClient
from app.infrastructure.external.gemini_client import GeminiClient
from app.infrastructure.external.model_clients import OutbreakModelClient, SegmentationClient
from app.infrastructure.external.weather_client import OpenMeteoDailyProvider, WeatherService
from app.infrastructure.reporting.pdf_report_generator import PdfReportGenerator
from app.infrastructure.repositories.ai_features_repository import (
    SqlAlchemyOutbreakRepository,
    SqlAlchemyRecoveryRepository,
    SqlAlchemySegmentationRepository,
)
from app.infrastructure.repositories.audit_log_repository import SqlAlchemyAuditLogRepository
from app.infrastructure.repositories.diagnosis_repository import SqlAlchemyDiagnosisRepository
from app.infrastructure.repositories.knowledge_base_repository import (
    SqlAlchemyDiseaseRepository,
    SqlAlchemyPlantRepository,
    SqlAlchemyTreatmentRepository,
)
from app.infrastructure.repositories.refresh_token_repository import SqlAlchemyRefreshTokenRepository
from app.infrastructure.repositories.user_repository import SqlAlchemyUserRepository
from app.infrastructure.security.jwt_service import JwtService, TokenError
from app.infrastructure.security.password_hasher import PasswordHasher
from app.infrastructure.storage.object_storage import LocalObjectStorage

settings = get_settings()

# --- Stateless singletons (no request state, safe to share) ---
_jwt_service = JwtService()
_password_hasher = PasswordHasher()
_weather_service = WeatherService()
_pdf_generator = PdfReportGenerator()
_ai_client = AiPipelineClient()
_gemini_service = GeminiAnalysisService(GeminiClient())
_storage = LocalObjectStorage(base_dir=settings.local_storage_dir)
# Optional AI models: loaded lazily once per worker, independent of each other.
_segmentation_client = SegmentationClient()
_outbreak_client = OutbreakModelClient()
_daily_weather = OpenMeteoDailyProvider()


# --- Repository providers ---
def get_user_repository(db: Session = Depends(get_db)) -> SqlAlchemyUserRepository:
    return SqlAlchemyUserRepository(db)


def get_refresh_token_repository(db: Session = Depends(get_db)) -> SqlAlchemyRefreshTokenRepository:
    return SqlAlchemyRefreshTokenRepository(db)


def get_plant_repository(db: Session = Depends(get_db)) -> SqlAlchemyPlantRepository:
    return SqlAlchemyPlantRepository(db)


def get_disease_repository(db: Session = Depends(get_db)) -> SqlAlchemyDiseaseRepository:
    return SqlAlchemyDiseaseRepository(db)


def get_treatment_repository(db: Session = Depends(get_db)) -> SqlAlchemyTreatmentRepository:
    return SqlAlchemyTreatmentRepository(db)


def get_diagnosis_repository(db: Session = Depends(get_db)) -> SqlAlchemyDiagnosisRepository:
    return SqlAlchemyDiagnosisRepository(db)


def get_audit_log_repository(db: Session = Depends(get_db)) -> SqlAlchemyAuditLogRepository:
    return SqlAlchemyAuditLogRepository(db)


def get_segmentation_repository(db: Session = Depends(get_db)) -> SqlAlchemySegmentationRepository:
    return SqlAlchemySegmentationRepository(db)


def get_recovery_repository(db: Session = Depends(get_db)) -> SqlAlchemyRecoveryRepository:
    return SqlAlchemyRecoveryRepository(db)


def get_outbreak_repository(db: Session = Depends(get_db)) -> SqlAlchemyOutbreakRepository:
    return SqlAlchemyOutbreakRepository(db)


# --- Application service providers ---
def get_recovery_service(
    repo: SqlAlchemyRecoveryRepository = Depends(get_recovery_repository),
    diagnosis_repo: SqlAlchemyDiagnosisRepository = Depends(get_diagnosis_repository),
    segmentation_repo: SqlAlchemySegmentationRepository = Depends(get_segmentation_repository),
) -> RecoveryService:
    return RecoveryService(repo, diagnosis_repo, segmentation_repo)


def get_outbreak_service(repo: SqlAlchemyOutbreakRepository = Depends(get_outbreak_repository)) -> OutbreakService:
    return OutbreakService(repo, _outbreak_client, _daily_weather)


def get_reference_service(
    db: Session = Depends(get_db),
    plant_repo: SqlAlchemyPlantRepository = Depends(get_plant_repository),
    disease_repo: SqlAlchemyDiseaseRepository = Depends(get_disease_repository),
    treatment_repo: SqlAlchemyTreatmentRepository = Depends(get_treatment_repository),
    audit_repo: SqlAlchemyAuditLogRepository = Depends(get_audit_log_repository),
):
    from app.application.services.reference_service import ReferenceService
    from app.infrastructure.repositories.knowledge_reference_repository import SqlAlchemyKnowledgeReferenceRepository

    return ReferenceService(SqlAlchemyKnowledgeReferenceRepository(db), plant_repo, disease_repo, treatment_repo, audit_repo)


def get_report_service(
    db: Session = Depends(get_db),
    diagnosis_repo: SqlAlchemyDiagnosisRepository = Depends(get_diagnosis_repository),
    disease_repo: SqlAlchemyDiseaseRepository = Depends(get_disease_repository),
    treatment_repo: SqlAlchemyTreatmentRepository = Depends(get_treatment_repository),
    segmentation_repo: SqlAlchemySegmentationRepository = Depends(get_segmentation_repository),
    recovery_service: RecoveryService = Depends(get_recovery_service),
    outbreak_service: OutbreakService = Depends(get_outbreak_service),
    reference_service=Depends(get_reference_service),
):
    from app.application.reporting.service import ReportService
    from app.infrastructure.repositories.report_center_repository import SqlAlchemyReportCenterRepository

    return ReportService(SqlAlchemyReportCenterRepository(db), diagnosis_repo, disease_repo, treatment_repo,
                         segmentation_repo, recovery_service, outbreak_service, _storage,
                         reference_service=reference_service)


def get_segmentation_client() -> SegmentationClient:
    return _segmentation_client


def get_outbreak_client() -> OutbreakModelClient:
    return _outbreak_client


def get_auth_service(
    user_repo: SqlAlchemyUserRepository = Depends(get_user_repository),
    token_repo: SqlAlchemyRefreshTokenRepository = Depends(get_refresh_token_repository),
) -> AuthService:
    return AuthService(user_repo, token_repo, _password_hasher, _jwt_service)


def get_scan_orchestrator(
    plant_repo: SqlAlchemyPlantRepository = Depends(get_plant_repository),
    disease_repo: SqlAlchemyDiseaseRepository = Depends(get_disease_repository),
    treatment_repo: SqlAlchemyTreatmentRepository = Depends(get_treatment_repository),
    diagnosis_repo: SqlAlchemyDiagnosisRepository = Depends(get_diagnosis_repository),
    segmentation_repo: SqlAlchemySegmentationRepository = Depends(get_segmentation_repository),
    recovery_service: RecoveryService = Depends(get_recovery_service),
    outbreak_service: OutbreakService = Depends(get_outbreak_service),
) -> ScanOrchestrator:
    return ScanOrchestrator(
        storage=_storage, ai_client=_ai_client, plant_repo=plant_repo, disease_repo=disease_repo,
        treatment_repo=treatment_repo, diagnosis_repo=diagnosis_repo, weather_service=_weather_service,
        pdf_generator=_pdf_generator, gemini_service=_gemini_service,
        segmentation_client=_segmentation_client, segmentation_repo=segmentation_repo,
        outbreak_service=outbreak_service, recovery_service=recovery_service,
    )


def get_knowledge_base_service(
    plant_repo: SqlAlchemyPlantRepository = Depends(get_plant_repository),
    disease_repo: SqlAlchemyDiseaseRepository = Depends(get_disease_repository),
    treatment_repo: SqlAlchemyTreatmentRepository = Depends(get_treatment_repository),
    audit_repo: SqlAlchemyAuditLogRepository = Depends(get_audit_log_repository),
) -> KnowledgeBaseService:
    return KnowledgeBaseService(plant_repo, disease_repo, treatment_repo, audit_repo)


def get_dashboard_service(
    diagnosis_repo: SqlAlchemyDiagnosisRepository = Depends(get_diagnosis_repository),
) -> DashboardService:
    return DashboardService(diagnosis_repo)


def get_admin_service(
    user_repo: SqlAlchemyUserRepository = Depends(get_user_repository),
    audit_repo: SqlAlchemyAuditLogRepository = Depends(get_audit_log_repository),
) -> AdminService:
    return AdminService(user_repo, audit_repo)


def get_weather_service() -> WeatherService:
    return _weather_service


def get_object_storage() -> LocalObjectStorage:
    return _storage


# --- Auth dependencies (NFR-SEC-3, BR3/BR4) ---
def get_current_user(
    authorization: Optional[str] = Header(default=None),
    user_repo: SqlAlchemyUserRepository = Depends(get_user_repository),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("Missing or malformed Authorization header.")
    raw_token = authorization.split(" ", 1)[1].strip()

    try:
        payload = _jwt_service.decode_access_token(raw_token)
    except TokenError as exc:
        raise TokenExpiredOrInvalidError(str(exc))

    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError):
        raise TokenExpiredOrInvalidError("Malformed token payload.")

    user = user_repo.get_by_id(user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account not found or inactive.")
    return user


def require_roles(*allowed_roles: UserRole):
    """Factory for a role-gating dependency (BR3/BR4): e.g.
    `Depends(require_roles(UserRole.ADMIN))`. Role checks always happen server-side,
    never trusted from client-supplied data (NFR-SEC-3 / API spec §11)."""

    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise AuthorizationError(
                f"This action requires one of the following roles: {[r.value for r in allowed_roles]}."
            )
        return current_user

    return _dependency
