"""
Repositories for the AI features (localization, recovery, outbreak).

They return ORM rows (sessions use expire_on_commit=False, so rows stay readable after
commit); all business rules — ownership, privacy thresholds, assessment logic — live
in the application services, not here. Every query that touches user data is scoped
by an explicit owner or diagnosis id passed in by the service.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, case, delete, func, select
from sqlalchemy.orm import Session

from app.infrastructure.db.models.ai_features_model import (
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
from app.infrastructure.db.models.diagnosis_model import DiagnosisModel


class SqlAlchemySegmentationRepository:
    def __init__(self, db: Session):
        self.db = db

    def save(self, row: DiagnosisSegmentationModel) -> DiagnosisSegmentationModel:
        self.db.add(row)
        self.db.commit()
        return row

    def get_for_diagnosis(self, diagnosis_id: UUID) -> Optional[DiagnosisSegmentationModel]:
        return self.db.execute(select(DiagnosisSegmentationModel).where(
            DiagnosisSegmentationModel.diagnosis_id == diagnosis_id)).scalar_one_or_none()

    def get_for_diagnoses(self, ids: Iterable[UUID]) -> Dict[UUID, DiagnosisSegmentationModel]:
        ids = list(ids)
        if not ids:
            return {}
        rows = self.db.execute(select(DiagnosisSegmentationModel).where(
            DiagnosisSegmentationModel.diagnosis_id.in_(ids))).scalars().all()
        return {r.diagnosis_id: r for r in rows}


class SqlAlchemyRecoveryRepository:
    def __init__(self, db: Session):
        self.db = db

    def commit(self) -> None:
        self.db.commit()

    def add(self, row):
        self.db.add(row)
        self.db.commit()
        return row

    def delete(self, row) -> None:
        self.db.delete(row)
        self.db.commit()

    # ------------------------------------------------------------- plants
    def get_owned_plant(self, plant_id: UUID, owner_id: UUID) -> Optional[TrackedPlantModel]:
        return self.db.execute(select(TrackedPlantModel).where(
            TrackedPlantModel.id == plant_id, TrackedPlantModel.owner_id == owner_id)).scalar_one_or_none()

    def list_owned_plants(self, owner_id: UUID, status: Optional[str], page: int, page_size: int) -> Tuple[List[TrackedPlantModel], int]:
        stmt = select(TrackedPlantModel).where(TrackedPlantModel.owner_id == owner_id)
        if status:
            stmt = stmt.where(TrackedPlantModel.status == status)
        total = self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = self.db.execute(stmt.order_by(TrackedPlantModel.created_at.desc(), TrackedPlantModel.id)
                               .offset((page - 1) * page_size).limit(page_size)).scalars().all()
        return list(rows), total

    # ------------------------------------------------------------- scan links
    def link_for_diagnosis(self, diagnosis_id: UUID) -> Optional[TrackedPlantScanModel]:
        return self.db.execute(select(TrackedPlantScanModel).where(
            TrackedPlantScanModel.diagnosis_id == diagnosis_id)).scalar_one_or_none()

    def links_with_diagnoses(self, plant_id: UUID) -> List[Tuple[TrackedPlantScanModel, DiagnosisModel]]:
        rows = self.db.execute(
            select(TrackedPlantScanModel, DiagnosisModel)
            .join(DiagnosisModel, DiagnosisModel.id == TrackedPlantScanModel.diagnosis_id)
            .where(TrackedPlantScanModel.tracked_plant_id == plant_id)
            .order_by(DiagnosisModel.diagnosed_at, DiagnosisModel.id)).all()
        return [(link, diag) for link, diag in rows]

    def plant_summaries(self, plant_ids: List[UUID]) -> Dict[UUID, dict]:
        if not plant_ids:
            return {}
        out = {pid: {"scan_count": 0, "last_scan_at": None, "latest_status": None, "next_reminder_on": None}
               for pid in plant_ids}
        for pid, count, last in self.db.execute(
                select(TrackedPlantScanModel.tracked_plant_id, func.count(), func.max(DiagnosisModel.diagnosed_at))
                .join(DiagnosisModel, DiagnosisModel.id == TrackedPlantScanModel.diagnosis_id)
                .where(TrackedPlantScanModel.tracked_plant_id.in_(plant_ids))
                .group_by(TrackedPlantScanModel.tracked_plant_id)).all():
            out[pid].update(scan_count=count, last_scan_at=last)
        for pid, due in self.db.execute(
                select(FollowUpReminderModel.tracked_plant_id, func.min(FollowUpReminderModel.due_on))
                .where(FollowUpReminderModel.tracked_plant_id.in_(plant_ids), FollowUpReminderModel.status == "pending")
                .group_by(FollowUpReminderModel.tracked_plant_id)).all():
            out[pid]["next_reminder_on"] = due
        for pid in plant_ids:
            latest = self.latest_assessment(pid)
            out[pid]["latest_status"] = latest.status if latest else None
        return out

    # ------------------------------------------------------------- treatments / reminders
    def list_treatments(self, plant_id: UUID) -> List[TreatmentRecordModel]:
        return list(self.db.execute(select(TreatmentRecordModel).where(TreatmentRecordModel.tracked_plant_id == plant_id)
                                    .order_by(TreatmentRecordModel.applied_on.desc(), TreatmentRecordModel.created_at.desc())).scalars())

    def get_treatment(self, plant_id: UUID, treatment_id: UUID) -> Optional[TreatmentRecordModel]:
        return self.db.execute(select(TreatmentRecordModel).where(
            TreatmentRecordModel.id == treatment_id, TreatmentRecordModel.tracked_plant_id == plant_id)).scalar_one_or_none()

    def list_reminders(self, plant_id: UUID) -> List[FollowUpReminderModel]:
        return list(self.db.execute(select(FollowUpReminderModel).where(FollowUpReminderModel.tracked_plant_id == plant_id)
                                    .order_by(FollowUpReminderModel.due_on, FollowUpReminderModel.created_at)).scalars())

    def get_reminder(self, plant_id: UUID, reminder_id: UUID) -> Optional[FollowUpReminderModel]:
        return self.db.execute(select(FollowUpReminderModel).where(
            FollowUpReminderModel.id == reminder_id, FollowUpReminderModel.tracked_plant_id == plant_id)).scalar_one_or_none()

    def owner_reminders(self, owner_id: UUID, statuses: List[str], due_before: Optional[date], page: int,
                        page_size: int) -> Tuple[List[Tuple[FollowUpReminderModel, TrackedPlantModel]], int]:
        stmt = (select(FollowUpReminderModel, TrackedPlantModel)
                .join(TrackedPlantModel, TrackedPlantModel.id == FollowUpReminderModel.tracked_plant_id)
                .where(TrackedPlantModel.owner_id == owner_id, FollowUpReminderModel.status.in_(statuses)))
        if due_before:
            stmt = stmt.where(FollowUpReminderModel.due_on <= due_before)
        total = self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = self.db.execute(stmt.order_by(FollowUpReminderModel.due_on).offset((page - 1) * page_size).limit(page_size)).all()
        return [(r, p) for r, p in rows], total

    # ------------------------------------------------------------- assessments / timeline
    def latest_assessment(self, plant_id: UUID) -> Optional[RecoveryAssessmentModel]:
        return self.db.execute(select(RecoveryAssessmentModel).where(RecoveryAssessmentModel.tracked_plant_id == plant_id)
                               .order_by(RecoveryAssessmentModel.created_at.desc()).limit(1)).scalar_one_or_none()

    def add_event(self, plant_id: UUID, event_type: str, commit: bool = True, **refs) -> PlantTimelineEventModel:
        details = refs.pop("details", None)
        row = PlantTimelineEventModel(tracked_plant_id=plant_id, event_type=event_type, details_json=details,
                                      occurred_at=datetime.now(timezone.utc), **refs)
        self.db.add(row)
        if commit:
            self.db.commit()
        return row

    def list_events(self, plant_id: UUID, page: int, page_size: int) -> Tuple[List[PlantTimelineEventModel], int]:
        stmt = select(PlantTimelineEventModel).where(PlantTimelineEventModel.tracked_plant_id == plant_id)
        total = self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = self.db.execute(stmt.order_by(PlantTimelineEventModel.occurred_at.desc(), PlantTimelineEventModel.id)
                               .offset((page - 1) * page_size).limit(page_size)).scalars().all()
        return list(rows), total


class SqlAlchemyOutbreakRepository:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------- areas
    def get_area(self, area_id: UUID) -> Optional[GeoAreaModel]:
        return self.db.get(GeoAreaModel, area_id)

    def get_area_by_key(self, key: str) -> Optional[GeoAreaModel]:
        return self.db.execute(select(GeoAreaModel).where(GeoAreaModel.grid_key == key)).scalar_one_or_none()

    def get_or_create_area(self, cell) -> GeoAreaModel:
        existing = self.get_area_by_key(cell.key)
        if existing:
            return existing
        lat, lon = cell.center
        row = GeoAreaModel(grid_key=cell.key, resolution_deg=cell.resolution, lat_index=cell.lat_index,
                           lon_index=cell.lon_index, south=cell.south, west=cell.west, north=cell.north,
                           east=cell.east, center_lat=lat, center_lon=lon)
        self.db.add(row)
        self.db.flush()
        return row

    def areas_by_keys(self, keys: List[str]) -> List[GeoAreaModel]:
        if not keys:
            return []
        return list(self.db.execute(select(GeoAreaModel).where(GeoAreaModel.grid_key.in_(keys))).scalars())

    # ------------------------------------------------------------- observations
    def add_observation(self, row: DiseaseObservationModel, commit: bool = True) -> DiseaseObservationModel:
        self.db.add(row)
        if commit:
            self.db.commit()
        return row

    def observation_for_diagnosis(self, diagnosis_id: UUID) -> Optional[DiseaseObservationModel]:
        return self.db.execute(select(DiseaseObservationModel).where(
            DiseaseObservationModel.diagnosis_id == diagnosis_id)).scalar_one_or_none()

    def observations(self, area_ids: List[UUID], crop: str, since: date) -> List[DiseaseObservationModel]:
        if not area_ids:
            return []
        return list(self.db.execute(select(DiseaseObservationModel).where(
            DiseaseObservationModel.area_id.in_(area_ids), DiseaseObservationModel.crop == crop,
            DiseaseObservationModel.observed_on >= since).order_by(DiseaseObservationModel.observed_on)).scalars())

    def app_contributors(self, area_ids: List[UUID], crop: str, since: date) -> Dict[UUID, int]:
        """Distinct users behind the app-scan observations of `crop` in each area since
        `since` (areas without any are left out)."""
        if not area_ids:
            return {}
        o, d = DiseaseObservationModel, DiagnosisModel
        rows = self.db.execute(
            select(o.area_id, func.count(func.distinct(d.user_id)))
            .join(d, d.id == o.diagnosis_id)
            .where(o.area_id.in_(area_ids), o.source == "app_scan", o.crop == crop, o.observed_on >= since)
            .group_by(o.area_id)).all()
        return {area_id: int(n) for area_id, n in rows}

    def aggregate(self, crop: Optional[str], disease: Optional[str], date_from: date, date_to: date,
                  bbox: Optional[Tuple[float, float, float, float]], page: int, page_size: int,
                  area_id: Optional[UUID] = None):
        """Per-area counts for the map. App scans of the crop are inspections; they are
        positive for `disease` only when that disease was predicted. Dataset rows
        are targeted inspections for their own disease."""
        o, d, a = DiseaseObservationModel, DiagnosisModel, GeoAreaModel
        is_app = o.source == "app_scan"
        app_positive = and_(is_app, o.is_positive, o.disease == disease) if disease else and_(is_app, o.is_positive)
        dataset_match = and_(o.source == "dataset", o.disease == disease) if disease else (o.source == "dataset")
        stmt = (select(a, func.sum(case((is_app, 1), else_=0)).label("app_inspections"),
                       func.sum(case((app_positive, 1), else_=0)).label("app_positives"),
                       func.count(func.distinct(d.user_id)).label("app_contributors"),
                       func.sum(case((dataset_match, o.inspected_count), else_=0)).label("dataset_inspections"),
                       func.sum(case((dataset_match, o.positive_count), else_=0)).label("dataset_positives"),
                       func.max(o.observed_on).label("latest_observation"),
                       func.max(case((o.source == "dataset", o.observed_on), else_=None)).label("latest_dataset_observation"))
                .join(o, o.area_id == a.id).outerjoin(d, d.id == o.diagnosis_id)
                .where(o.observed_on >= date_from, o.observed_on <= date_to))
        if crop:
            stmt = stmt.where(o.crop == crop)
        if area_id:
            stmt = stmt.where(a.id == area_id)
        if bbox:
            west, south, east, north = bbox
            stmt = stmt.where(a.center_lon >= west, a.center_lon <= east, a.center_lat >= south, a.center_lat <= north)
        stmt = stmt.group_by(a.id)
        total = self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = self.db.execute(stmt.order_by(a.grid_key).offset((page - 1) * page_size).limit(page_size)).all()
        return rows, total

    def readiness_counts(self) -> dict:
        o = DiseaseObservationModel
        by_source = dict(self.db.execute(select(o.source, func.count()).group_by(o.source)).all())
        first, last = self.db.execute(select(func.min(o.observed_on), func.max(o.observed_on))).one()
        return {"app_scan_observations": by_source.get("app_scan", 0), "dataset_observations": by_source.get("dataset", 0),
                "areas_with_observations": self.db.execute(select(func.count(func.distinct(o.area_id)))).scalar_one(),
                "first_observation": first, "last_observation": last,
                "located_diagnoses": self.db.execute(select(func.count()).select_from(DiagnosisModel)
                                                     .where(DiagnosisModel.location_lat.isnot(None))).scalar_one()}

    def filter_values(self) -> dict:
        o = DiseaseObservationModel
        pairs = self.db.execute(select(o.crop, o.disease).distinct().order_by(o.crop, o.disease)).all()
        return {"crops": sorted({c for c, _ in pairs}), "pairs": [{"crop": c, "disease": d} for c, d in pairs]}

    # ------------------------------------------------------------- weather
    def weather_days(self, area_id: UUID, start: date, end: date) -> List[WeatherObservationModel]:
        return list(self.db.execute(select(WeatherObservationModel).where(
            WeatherObservationModel.area_id == area_id, WeatherObservationModel.day >= start,
            WeatherObservationModel.day <= end).order_by(WeatherObservationModel.day)).scalars())

    def upsert_weather(self, area_id: UUID, records) -> None:
        days = {(r.day, r.kind) for r in records}
        if not days:
            return
        # Replace cached rows for these days (a day moves from forecast to observed over time).
        self.db.execute(delete(WeatherObservationModel).where(
            WeatherObservationModel.area_id == area_id, WeatherObservationModel.day.in_({d for d, _ in days})))
        now = datetime.now(timezone.utc)
        for r in records:
            self.db.add(WeatherObservationModel(
                area_id=area_id, day=r.day, kind=r.kind, source=r.source, temperature_mean_c=r.temperature_mean_c,
                temperature_min_c=r.temperature_min_c, temperature_max_c=r.temperature_max_c,
                relative_humidity_mean_pct=r.relative_humidity_mean_pct, rh_hours_ge_90=r.rh_hours_ge_90,
                precipitation_mm=r.precipitation_mm, retrieved_at=now))
        self.db.commit()

    # ------------------------------------------------------------- predictions
    def add_prediction(self, row: OutbreakPredictionModel) -> OutbreakPredictionModel:
        self.db.add(row)
        self.db.commit()
        return row

    def get_prediction(self, prediction_id: UUID) -> Optional[OutbreakPredictionModel]:
        return self.db.get(OutbreakPredictionModel, prediction_id)

    def list_predictions(self, area_id: Optional[UUID], crop: Optional[str], disease: Optional[str], page: int,
                         page_size: int) -> Tuple[List[OutbreakPredictionModel], int]:
        p = OutbreakPredictionModel
        stmt = select(p)
        for column, value in ((p.area_id, area_id), (p.crop, crop), (p.disease, disease)):
            if value:
                stmt = stmt.where(column == value)
        total = self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = self.db.execute(stmt.order_by(p.created_at.desc(), p.id).offset((page - 1) * page_size).limit(page_size)).scalars().all()
        return list(rows), total

    def latest_predictions(self, area_ids: List[UUID], crop: str, disease: str, horizon_days: int,
                           since: datetime) -> Dict[UUID, OutbreakPredictionModel]:
        if not area_ids:
            return {}
        p = OutbreakPredictionModel
        rows = self.db.execute(select(p).where(p.area_id.in_(area_ids), p.crop == crop, p.disease == disease,
                                               p.horizon_days == horizon_days, p.created_at >= since)
                               .order_by(p.created_at.desc())).scalars().all()
        latest: Dict[UUID, OutbreakPredictionModel] = {}
        for row in rows:
            latest.setdefault(row.area_id, row)
        return latest
