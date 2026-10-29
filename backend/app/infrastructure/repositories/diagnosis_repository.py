"""SQLAlchemy implementation of IDiagnosisRepository, including dashboard aggregation
(FR-DASH-1..3). Uses live aggregate queries rather than the materialized view directly
so it also works against the SQLite test backend (materialized views are Postgres-
only); the Postgres materialized view `mv_dashboard_monthly_stats` remains the
production performance optimization referenced in NFR-PERF-3 for large accounts, and
this repository can be extended to read from it directly once query volume warrants."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.domain.entities.diagnosis import AiAnalysis, Diagnosis, PestDetection, Recommendation, Report, SeverityLevel, WeatherSnapshot
from app.domain.repositories.interfaces import IDiagnosisRepository
from app.infrastructure.db.models.diagnosis_model import (
    AiAnalysisModel,
    DiagnosisModel,
    PestDetectionModel,
    RecommendationModel,
    ReportModel,
    WeatherSnapshotModel,
)
from app.infrastructure.db.models.knowledge_base_model import DiseaseModel, PlantModel


def _like(term: str) -> str:
    """ILIKE pattern for a user-supplied search term with LIKE wildcards escaped."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _start_of_day(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def _to_entity(m: DiagnosisModel) -> Diagnosis:
    return Diagnosis(
        id=m.id, user_id=m.user_id, plant_id=m.plant_id, disease_id=m.disease_id,
        confidence_score=float(m.confidence_score),
        severity_level=SeverityLevel(m.severity_level) if m.severity_level else None,
        affected_area_pct=float(m.affected_area_pct) if m.affected_area_pct is not None else None,
        healthy_area_pct=float(m.healthy_area_pct) if m.healthy_area_pct is not None else None,
        original_image_ref=m.original_image_ref, roi_image_ref=m.roi_image_ref,
        heatmap_image_ref=m.heatmap_image_ref, low_confidence_flag=m.low_confidence_flag,
        unrecognized_plant=m.unrecognized_plant,
        location_lat=float(m.location_lat) if m.location_lat is not None else None,
        location_lon=float(m.location_lon) if m.location_lon is not None else None,
        supersedes_diagnosis_id=m.supersedes_diagnosis_id, diagnosed_at=m.diagnosed_at,
        plant_profile_id=m.plant_profile_id,
        decision_status=m.decision_status,
        predicted_label=m.predicted_label,
        candidates=m.candidates_json or [],
        decision=m.decision_json or {},
        image_quality=m.image_quality_json or {},
        explanation=m.explanation_json or {},
        segmentation=m.segmentation_json or {},
        segmentation_mask_ref=m.segmentation_mask_ref,
        segmentation_overlay_ref=m.segmentation_overlay_ref,
        severity_method=m.severity_method,
        model_version=m.model_version,
        pipeline_version=m.pipeline_version,
        differential=m.differential_json or {},
        pest_detections=[
            PestDetection(id=p.id, diagnosis_id=p.diagnosis_id, pest_name=p.pest_name,
                          confidence=float(p.confidence), bbox=p.bbox_json)
            for p in (m.pest_detections or [])
        ],
        weather_snapshot=(
            WeatherSnapshot(
                id=m.weather_snapshot.id, diagnosis_id=m.weather_snapshot.diagnosis_id,
                temperature_c=float(m.weather_snapshot.temperature_c) if m.weather_snapshot.temperature_c is not None else None,
                humidity_pct=float(m.weather_snapshot.humidity_pct) if m.weather_snapshot.humidity_pct is not None else None,
                wind_speed_kmh=float(m.weather_snapshot.wind_speed_kmh) if m.weather_snapshot.wind_speed_kmh is not None else None,
                rain_probability_pct=float(m.weather_snapshot.rain_probability_pct) if m.weather_snapshot.rain_probability_pct is not None else None,
                uv_index=float(m.weather_snapshot.uv_index) if m.weather_snapshot.uv_index is not None else None,
                retrieved_at=m.weather_snapshot.retrieved_at,
            ) if m.weather_snapshot else None
        ),
        recommendation=(
            Recommendation(id=m.recommendation.id, diagnosis_id=m.recommendation.diagnosis_id,
                            irrigation_advice=m.recommendation.irrigation_advice,
                            spraying_advice=m.recommendation.spraying_advice,
                            fertilizer_advice=m.recommendation.fertilizer_advice)
            if m.recommendation else None
        ),
        report=(
            Report(id=m.report.id, diagnosis_id=m.report.diagnosis_id, file_ref=m.report.file_ref,
                   qr_code_ref=m.report.qr_code_ref, generated_at=m.report.generated_at)
            if m.report else None
        ),
        ai_analysis=(
            AiAnalysis(
                id=m.ai_analysis.id, diagnosis_id=m.ai_analysis.diagnosis_id, status=m.ai_analysis.status,
                diagnosis_explanation=m.ai_analysis.diagnosis_explanation,
                observed_symptoms=m.ai_analysis.observed_symptoms_json or [],
                cv_consistency=m.ai_analysis.cv_consistency,
                confidence_assessment=m.ai_analysis.confidence_assessment,
                severity_explanation=m.ai_analysis.severity_explanation,
                treatment_guidance=m.ai_analysis.treatment_guidance_json or [],
                prevention_guidance=m.ai_analysis.prevention_guidance_json or [],
                environmental_risk=m.ai_analysis.environmental_risk,
                urgency=m.ai_analysis.urgency,
                model_name=m.ai_analysis.model_name,
                message=m.ai_analysis.message,
                generated_at=m.ai_analysis.generated_at,
            ) if m.ai_analysis else None
        ),
    )


class SqlAlchemyDiagnosisRepository(IDiagnosisRepository):
    def __init__(self, db: Session):
        self.db = db

    def create(self, diagnosis: Diagnosis) -> Diagnosis:
        model = DiagnosisModel(
            user_id=diagnosis.user_id, plant_id=diagnosis.plant_id, disease_id=diagnosis.disease_id,
            confidence_score=diagnosis.confidence_score,
            severity_level=diagnosis.severity_level.value if diagnosis.severity_level else None,
            affected_area_pct=diagnosis.affected_area_pct, healthy_area_pct=diagnosis.healthy_area_pct,
            original_image_ref=diagnosis.original_image_ref, roi_image_ref=diagnosis.roi_image_ref,
            heatmap_image_ref=diagnosis.heatmap_image_ref, low_confidence_flag=diagnosis.low_confidence_flag,
            unrecognized_plant=diagnosis.unrecognized_plant, location_lat=diagnosis.location_lat,
            location_lon=diagnosis.location_lon, supersedes_diagnosis_id=diagnosis.supersedes_diagnosis_id,
            plant_profile_id=diagnosis.plant_profile_id, decision_status=diagnosis.decision_status,
            predicted_label=diagnosis.predicted_label, candidates_json=diagnosis.candidates or None,
            decision_json=diagnosis.decision or None, image_quality_json=diagnosis.image_quality or None,
            explanation_json=diagnosis.explanation or None, segmentation_json=diagnosis.segmentation or None,
            segmentation_mask_ref=diagnosis.segmentation_mask_ref,
            segmentation_overlay_ref=diagnosis.segmentation_overlay_ref,
            severity_method=diagnosis.severity_method, model_version=diagnosis.model_version,
            pipeline_version=diagnosis.pipeline_version, differential_json=diagnosis.differential or None,
        )
        self.db.add(model)
        self.db.flush()  # obtain model.id before adding children

        for pest in diagnosis.pest_detections:
            self.db.add(PestDetectionModel(diagnosis_id=model.id, pest_name=pest.pest_name,
                                            confidence=pest.confidence, bbox_json=pest.bbox))
        if diagnosis.weather_snapshot:
            ws = diagnosis.weather_snapshot
            self.db.add(WeatherSnapshotModel(
                diagnosis_id=model.id, temperature_c=ws.temperature_c, humidity_pct=ws.humidity_pct,
                wind_speed_kmh=ws.wind_speed_kmh, rain_probability_pct=ws.rain_probability_pct,
                uv_index=ws.uv_index, retrieved_at=ws.retrieved_at,
            ))
        if diagnosis.recommendation:
            rec = diagnosis.recommendation
            self.db.add(RecommendationModel(
                diagnosis_id=model.id, irrigation_advice=rec.irrigation_advice,
                spraying_advice=rec.spraying_advice, fertilizer_advice=rec.fertilizer_advice,
            ))
        if diagnosis.report:
            rpt = diagnosis.report
            self.db.add(ReportModel(diagnosis_id=model.id, file_ref=rpt.file_ref, qr_code_ref=rpt.qr_code_ref))
        if diagnosis.ai_analysis:
            aa = diagnosis.ai_analysis
            self.db.add(AiAnalysisModel(
                diagnosis_id=model.id, status=aa.status, diagnosis_explanation=aa.diagnosis_explanation,
                observed_symptoms_json=aa.observed_symptoms or None, cv_consistency=aa.cv_consistency,
                confidence_assessment=aa.confidence_assessment, severity_explanation=aa.severity_explanation,
                treatment_guidance_json=aa.treatment_guidance or None,
                prevention_guidance_json=aa.prevention_guidance or None,
                environmental_risk=aa.environmental_risk, urgency=aa.urgency,
                model_name=aa.model_name, message=aa.message,
            ))

        self.db.commit()
        self.db.refresh(model)
        return self.get_by_id(model.id)

    def get_by_id(self, diagnosis_id: UUID) -> Optional[Diagnosis]:
        stmt = (
            select(DiagnosisModel)
            .options(
                joinedload(DiagnosisModel.pest_detections),
                joinedload(DiagnosisModel.weather_snapshot),
                joinedload(DiagnosisModel.recommendation),
                joinedload(DiagnosisModel.report),
                joinedload(DiagnosisModel.ai_analysis),
            )
            .where(DiagnosisModel.id == diagnosis_id)
        )
        model = self.db.execute(stmt).unique().scalar_one_or_none()
        return _to_entity(model) if model else None

    def list_for_user(self, user_id: UUID, plant: Optional[str], disease: Optional[str],
                       date_from: Optional[date], date_to: Optional[date],
                       page: int, page_size: int, decision_status: Optional[str] = None,
                       plant_profile_id: Optional[UUID] = None,
                       unassigned_only: bool = False) -> Tuple[List[Diagnosis], int]:
        stmt = select(DiagnosisModel).where(DiagnosisModel.user_id == user_id)
        if plant:
            stmt = stmt.outerjoin(PlantModel, DiagnosisModel.plant_id == PlantModel.id).where(
                or_(PlantModel.canonical_name.ilike(_like(plant), escape="\\"),
                    DiagnosisModel.predicted_label.ilike(_like(plant), escape="\\"))
            )
        if disease:
            stmt = stmt.outerjoin(DiseaseModel, DiagnosisModel.disease_id == DiseaseModel.id).where(
                or_(DiseaseModel.name.ilike(_like(disease), escape="\\"),
                    DiagnosisModel.predicted_label.ilike(_like(disease), escape="\\"))
            )
        if date_from:
            stmt = stmt.where(DiagnosisModel.diagnosed_at >= _start_of_day(date_from))
        if date_to:
            # inclusive of the whole `date_to` day
            stmt = stmt.where(DiagnosisModel.diagnosed_at < _start_of_day(date_to + timedelta(days=1)))
        if decision_status:
            stmt = stmt.where(DiagnosisModel.decision_status == decision_status)
        if plant_profile_id is not None:
            stmt = stmt.where(DiagnosisModel.plant_profile_id == plant_profile_id)
        elif unassigned_only:
            stmt = stmt.where(DiagnosisModel.plant_profile_id.is_(None))

        total = self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        stmt = stmt.order_by(DiagnosisModel.diagnosed_at.desc()).offset((page - 1) * page_size).limit(page_size)
        models = self.db.execute(stmt).scalars().all()
        return [_to_entity(m) for m in models], total

    def list_for_plant_profile(self, plant_profile_id: UUID, date_from: Optional[date] = None,
                               date_to: Optional[date] = None, decision_status: Optional[str] = None,
                               page: int = 1, page_size: int = 50,
                               ascending: bool = True) -> Tuple[List[Diagnosis], int]:
        stmt = select(DiagnosisModel).where(DiagnosisModel.plant_profile_id == plant_profile_id)
        if date_from:
            stmt = stmt.where(DiagnosisModel.diagnosed_at >= _start_of_day(date_from))
        if date_to:
            stmt = stmt.where(DiagnosisModel.diagnosed_at < _start_of_day(date_to + timedelta(days=1)))
        if decision_status:
            stmt = stmt.where(DiagnosisModel.decision_status == decision_status)
        total = self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        order = DiagnosisModel.diagnosed_at.asc() if ascending else DiagnosisModel.diagnosed_at.desc()
        stmt = stmt.order_by(order).offset((page - 1) * page_size).limit(page_size)
        models = self.db.execute(stmt).scalars().all()
        return [_to_entity(m) for m in models], total

    def set_plant_profile(self, diagnosis_id: UUID, plant_profile_id: Optional[UUID]) -> None:
        model = self.db.get(DiagnosisModel, diagnosis_id)
        if model is None:
            return
        model.plant_profile_id = plant_profile_id
        self.db.commit()

    def update_differential(self, diagnosis_id: UUID, differential: dict) -> None:
        """Differential-diagnosis context (follow-up answers and the hints derived from
        them) is the only part of an observation that changes after creation; the
        answers themselves are also kept as append-only follow_up notes."""
        model = self.db.get(DiagnosisModel, diagnosis_id)
        if model is None:
            return
        model.differential_json = differential
        self.db.commit()

    def dashboard_summary(self, user_id: Optional[UUID]) -> dict:
        base = select(DiagnosisModel)
        if user_id is not None:
            base = base.where(DiagnosisModel.user_id == user_id)

        total_scans = self.db.execute(select(func.count()).select_from(base.subquery())).scalar_one()

        # "Healthy" means the model CONFIDENTLY predicted a healthy class. It no longer
        # means "no disease record was found in the knowledge base" (which also
        # happens for every disease the admins have not yet documented).
        healthy_label = DiagnosisModel.predicted_label.like("%\\_\\_\\_healthy", escape="\\")
        healthy_stmt = base.where(DiagnosisModel.decision_status == "confident", healthy_label)
        healthy_count = self.db.execute(select(func.count()).select_from(healthy_stmt.subquery())).scalar_one()

        diseased_stmt = base.where(or_(
            DiagnosisModel.disease_id.isnot(None),
            and_(DiagnosisModel.decision_status == "confident", ~healthy_label),
        ))
        diseased_count = self.db.execute(select(func.count()).select_from(diseased_stmt.subquery())).scalar_one()

        uncertain_stmt = base.where(DiagnosisModel.decision_status.in_(("uncertain", "inconclusive")))
        uncertain_count = self.db.execute(select(func.count()).select_from(uncertain_stmt.subquery())).scalar_one()

        confident_stmt = base.where(DiagnosisModel.decision_status == "confident")
        confident_count = self.db.execute(select(func.count()).select_from(confident_stmt.subquery())).scalar_one()

        palm_stmt = (
            base.join(PlantModel, DiagnosisModel.plant_id == PlantModel.id)
            .where(PlantModel.canonical_name == "date_palm")
        )
        total_palm_scans = self.db.execute(select(func.count()).select_from(palm_stmt.subquery())).scalar_one()

        weevil_stmt = (
            base.join(DiseaseModel, DiagnosisModel.disease_id == DiseaseModel.id)
            .where(DiseaseModel.name.ilike("%red palm weevil%"))
        )
        red_palm_weevil_incidents = self.db.execute(select(func.count()).select_from(weevil_stmt.subquery())).scalar_one()

        # Most common CONFIDENT predictions (by model label), plus legacy rows that were
        # linked to a knowledge-base disease record.
        label_rows = self.db.execute(
            base.where(DiagnosisModel.decision_status == "confident", ~healthy_label,
                       DiagnosisModel.predicted_label.isnot(None))
            .with_only_columns(DiagnosisModel.predicted_label, func.count().label("cnt"))
            .group_by(DiagnosisModel.predicted_label)
        ).all()
        legacy_rows = self.db.execute(
            base.where(or_(DiagnosisModel.decision_status.is_(None), DiagnosisModel.decision_status == "legacy"))
            .join(DiseaseModel, DiagnosisModel.disease_id == DiseaseModel.id)
            .with_only_columns(DiseaseModel.name, func.count().label("cnt"))
            .group_by(DiseaseModel.name)
        ).all()
        counts: dict = {}
        for name, cnt in list(label_rows) + list(legacy_rows):
            counts[name] = counts.get(name, 0) + cnt
        most_common = [{"name": n, "count": c} for n, c in sorted(counts.items(), key=lambda kv: -kv[1])[:10]]

        monthly_stmt = (
            base.with_only_columns(
                func.strftime("%Y-%m", DiagnosisModel.diagnosed_at).label("month")
                if self.db.bind.dialect.name == "sqlite"
                else func.to_char(DiagnosisModel.diagnosed_at, "YYYY-MM").label("month"),
                func.count().label("cnt"),
            )
            .group_by("month")
            .order_by("month")
        )
        monthly_trend = [{"month": row[0], "scan_count": row[1]} for row in self.db.execute(monthly_stmt).all()]

        return {
            "total_scans": total_scans,
            "healthy_count": healthy_count,
            "diseased_count": diseased_count,
            "uncertain_count": uncertain_count,
            "confident_count": confident_count,
            "palm_disease_stats": {
                "total_palm_scans": total_palm_scans,
                "red_palm_weevil_incidents": red_palm_weevil_incidents,
            },
            "most_common_diseases": most_common,
            "monthly_trend": monthly_trend,
        }

    def attach_report(self, diagnosis_id: UUID, file_ref: str, qr_code_ref: str) -> Report:
        model = ReportModel(diagnosis_id=diagnosis_id, file_ref=file_ref, qr_code_ref=qr_code_ref)
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return Report(id=model.id, diagnosis_id=model.diagnosis_id, file_ref=model.file_ref,
                       qr_code_ref=model.qr_code_ref, generated_at=model.generated_at)

    def attach_ai_analysis(self, diagnosis_id: UUID, ai_analysis: AiAnalysis) -> AiAnalysis:
        model = AiAnalysisModel(
            diagnosis_id=diagnosis_id, status=ai_analysis.status,
            diagnosis_explanation=ai_analysis.diagnosis_explanation,
            observed_symptoms_json=ai_analysis.observed_symptoms or None,
            cv_consistency=ai_analysis.cv_consistency,
            confidence_assessment=ai_analysis.confidence_assessment,
            severity_explanation=ai_analysis.severity_explanation,
            treatment_guidance_json=ai_analysis.treatment_guidance or None,
            prevention_guidance_json=ai_analysis.prevention_guidance or None,
            environmental_risk=ai_analysis.environmental_risk,
            urgency=ai_analysis.urgency, model_name=ai_analysis.model_name,
            message=ai_analysis.message,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return AiAnalysis(
            id=model.id, diagnosis_id=model.diagnosis_id, status=model.status,
            diagnosis_explanation=model.diagnosis_explanation,
            observed_symptoms=model.observed_symptoms_json or [],
            cv_consistency=model.cv_consistency, confidence_assessment=model.confidence_assessment,
            severity_explanation=model.severity_explanation,
            treatment_guidance=model.treatment_guidance_json or [],
            prevention_guidance=model.prevention_guidance_json or [],
            environmental_risk=model.environmental_risk, urgency=model.urgency,
            model_name=model.model_name, message=model.message, generated_at=model.generated_at,
        )
