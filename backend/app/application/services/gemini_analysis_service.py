"""
GeminiAnalysisService — thin application-layer wrapper that turns a
GeminiAnalysisResult (infrastructure concern) into an AiAnalysis domain entity
(what ScanOrchestrator and the repositories work with), mirroring how
WeatherService/PdfReportGenerator are separate, injectable collaborators rather
than logic embedded directly in ScanOrchestrator.
"""
from __future__ import annotations

from typing import Optional

from app.domain.entities.diagnosis import AiAnalysis
from app.domain.repositories.interfaces import IDiseaseRepository, IPlantRepository, ITreatmentRepository
from app.infrastructure.external.gemini_client import GeminiClient, GeminiRequestContext


class GeminiAnalysisService:
    def __init__(self, client: Optional[GeminiClient] = None):
        self.client = client or GeminiClient()

    def analyze(
        self,
        ctx: GeminiRequestContext,
        plant_repo: IPlantRepository,
        disease_repo: IDiseaseRepository,
        treatment_repo: ITreatmentRepository,
    ) -> Optional[AiAnalysis]:
        """Returns None only when Gemini is disabled (no GEMINI_API_KEY) — in that
        case nothing should be persisted at all. A genuine attempt that failed
        still returns an AiAnalysis with status="unavailable" so the diagnosis
        record reflects that an analysis was tried (requirement: don't fabricate
        a fake success, but also don't silently pretend nothing happened)."""
        result = self.client.analyze(ctx, plant_repo, disease_repo, treatment_repo)

        if result.status == "disabled":
            return None

        if result.status == "unavailable" or result.analysis is None:
            return AiAnalysis(
                id=None, diagnosis_id=None, status="unavailable",
                message=result.message or "AI analysis temporarily unavailable.",
            )

        a = result.analysis
        return AiAnalysis(
            id=None, diagnosis_id=None, status="ok",
            diagnosis_explanation=a.diagnosis_explanation,
            observed_symptoms=a.observed_symptoms,
            cv_consistency=a.cv_consistency.value,
            confidence_assessment=a.confidence_assessment,
            severity_explanation=a.severity_explanation,
            treatment_guidance=a.treatment_guidance,
            prevention_guidance=a.prevention_guidance,
            environmental_risk=a.environmental_risk,
            urgency=a.urgency.value,
            model_name=result.model_name,
        )
