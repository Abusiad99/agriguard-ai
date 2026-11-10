"""
Import every ORM model here so `Base.metadata` is fully populated wherever
`app.infrastructure.db.models` is imported -- required by Alembic's autogenerate and
by the test suite's `Base.metadata.create_all()` against SQLite.
"""
from app.infrastructure.db.base import Base  # noqa: F401
from app.infrastructure.db.models.ai_features_model import (  # noqa: F401
    DiagnosisSegmentationModel,
    DiseaseObservationModel,
    FollowUpReminderModel,
    GeoAreaModel,
    OutbreakPredictionModel,
    PlantTimelineEventModel,
    RecoveryAssessmentModel,
    TrackedPlantModel,
    TrackedPlantScanModel,
    TreatmentRecordModel,
    WeatherObservationModel,
)
from app.infrastructure.db.models.diagnosis_model import (  # noqa: F401
    AuditLogModel,
    DiagnosisModel,
    PestDetectionModel,
    RecommendationModel,
    ReportModel,
    WeatherSnapshotModel,
)
from app.infrastructure.db.models.report_center_model import GeneratedReportModel, ReportShareModel  # noqa: F401
from app.infrastructure.db.models.knowledge_reference_model import (  # noqa: F401
    KnowledgeReferenceClaimModel,
    KnowledgeReferenceModel,
)
from app.infrastructure.db.models.knowledge_base_model import (  # noqa: F401
    DiseaseModel,
    PlantModel,
    TreatmentModel,
)
from app.infrastructure.db.models.user_model import (  # noqa: F401
    PasswordResetTokenModel,
    RefreshTokenModel,
    UserModel,
)

__all__ = [
    "Base",
    "UserModel",
    "RefreshTokenModel",
    "PasswordResetTokenModel",
    "PlantModel",
    "DiseaseModel",
    "TreatmentModel",
    "DiagnosisModel",
    "PestDetectionModel",
    "WeatherSnapshotModel",
    "RecommendationModel",
    "ReportModel",
    "AuditLogModel",
    "DiagnosisSegmentationModel",
    "TrackedPlantModel",
    "TrackedPlantScanModel",
    "TreatmentRecordModel",
    "FollowUpReminderModel",
    "RecoveryAssessmentModel",
    "PlantTimelineEventModel",
    "GeoAreaModel",
    "DiseaseObservationModel",
    "WeatherObservationModel",
    "OutbreakPredictionModel",
    "GeneratedReportModel",
    "ReportShareModel",
    "KnowledgeReferenceModel",
    "KnowledgeReferenceClaimModel",
]
