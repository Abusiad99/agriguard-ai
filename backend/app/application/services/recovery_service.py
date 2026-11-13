"""
Plant recovery monitoring (docs/features/plant-recovery-monitoring.md).

Ownership: every operation starts from `require_plant(owner, plant_id)`. A plant that
doesn't exist and one that belongs to someone else both raise NotFoundError, so ids
can't be probed. A diagnosis can be linked only to a plant of the same owner, and at
most to one plant. Diagnoses are referenced, never copied or modified.

Treatments are what the user recorded. Nothing here generates treatments or dosages;
the API marks them `source: "user_recorded"`.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.infrastructure.db.models.ai_features_model import (
    FollowUpReminderModel,
    RecoveryAssessmentModel,
    TrackedPlantModel,
    TrackedPlantScanModel,
    TreatmentRecordModel,
)
from app.infrastructure.external import ai_pipeline_client  # noqa: F401  (repo-root `ai` on sys.path)
from app.infrastructure.repositories.ai_features_repository import (
    SqlAlchemyRecoveryRepository,
    SqlAlchemySegmentationRepository,
)
from app.infrastructure.repositories.diagnosis_repository import SqlAlchemyDiagnosisRepository

from ai.recovery.engine import RecoveryRules, ScanSnapshot, assess

TREATMENT_STAGES = ("before_treatment", "during_treatment", "after_treatment", "unknown")
TREATMENT_CATEGORIES = ("organic", "chemical", "biological", "cultural", "other")
REMINDER_KINDS = ("next_scan", "treatment_follow_up")
REMINDER_STATUSES = ("pending", "completed", "dismissed")


class RecoveryService:
    def __init__(self, repo: SqlAlchemyRecoveryRepository, diagnosis_repo: SqlAlchemyDiagnosisRepository,
                 segmentation_repo: SqlAlchemySegmentationRepository, rules: Optional[RecoveryRules] = None):
        self.repo = repo
        self.diagnosis_repo = diagnosis_repo
        self.segmentation_repo = segmentation_repo
        self.rules = rules or RecoveryRules.load()

    # ------------------------------------------------------------------ plants
    def require_plant(self, owner_id: UUID, plant_id: UUID) -> TrackedPlantModel:
        plant = self.repo.get_owned_plant(plant_id, owner_id)
        if plant is None:
            raise NotFoundError("Tracked plant not found.")
        return plant

    def create_plant(self, owner_id: UUID, name: str, crop: Optional[str], species: Optional[str], notes: Optional[str],
                     location: Optional[tuple], initial_diagnosis_id: Optional[UUID]) -> TrackedPlantModel:
        initial = self._owned_diagnosis(owner_id, initial_diagnosis_id) if initial_diagnosis_id else None
        if initial is not None and self.repo.link_for_diagnosis(initial.id):
            raise ConflictError("That scan is already linked to a tracked plant.")
        plant = self.repo.add(TrackedPlantModel(
            owner_id=owner_id, name=name.strip(), crop=crop, species=species, notes=notes,
            location_lat=location[0] if location else None, location_lon=location[1] if location else None,
            initial_diagnosis_id=initial.id if initial else None))
        self.repo.add_event(plant.id, "plant_created", details={"name": plant.name})
        if initial is not None:
            self.link_scan(owner_id, plant.id, initial.id, "unknown", None)
        return plant

    def update_plant(self, owner_id: UUID, plant_id: UUID, changes: dict) -> TrackedPlantModel:
        plant = self.require_plant(owner_id, plant_id)
        if "location" in changes:
            loc = changes.pop("location")
            plant.location_lat, plant.location_lon = (loc[0], loc[1]) if loc else (None, None)
        for field in ("name", "crop", "species", "notes", "status"):
            if field in changes:
                setattr(plant, field, changes[field].strip() if field == "name" else changes[field])
        plant.updated_at = datetime.now(timezone.utc)
        self.repo.add_event(plant.id, "plant_updated", commit=False, details={"fields": sorted(changes)})
        self.repo.commit()
        return plant

    def list_plants(self, owner_id: UUID, status: Optional[str], page: int, page_size: int):
        plants, total = self.repo.list_owned_plants(owner_id, status, page, page_size)
        return plants, total, self.repo.plant_summaries([p.id for p in plants])

    # ------------------------------------------------------------------ scans
    def _owned_diagnosis(self, owner_id: UUID, diagnosis_id: UUID):
        diagnosis = self.diagnosis_repo.get_by_id(diagnosis_id)
        if diagnosis is None or diagnosis.user_id != owner_id:
            raise NotFoundError("Diagnosis not found.")
        return diagnosis

    def link_scan(self, owner_id: UUID, plant_id: UUID, diagnosis_id: UUID, stage: str, notes: Optional[str]) -> TrackedPlantScanModel:
        plant = self.require_plant(owner_id, plant_id)
        diagnosis = self._owned_diagnosis(owner_id, diagnosis_id)
        if stage not in TREATMENT_STAGES:
            raise ValidationError(f"treatment_stage must be one of {TREATMENT_STAGES}.")
        existing = self.repo.link_for_diagnosis(diagnosis.id)
        if existing is not None:
            if existing.tracked_plant_id == plant.id:
                return existing
            raise ConflictError("That scan is already linked to another tracked plant.")
        try:
            link = self.repo.add(TrackedPlantScanModel(tracked_plant_id=plant.id, diagnosis_id=diagnosis.id,
                                                       treatment_stage=stage, notes=notes))
        except IntegrityError:
            # Two requests linked the same scan at the same moment; the unique constraint on
            # diagnosis_id kept one. Answer like the check above instead of a server error.
            self.repo.db.rollback()
            existing = self.repo.link_for_diagnosis(diagnosis.id)
            if existing is not None and existing.tracked_plant_id == plant.id:
                return existing
            raise ConflictError("That scan is already linked to another tracked plant.")
        self.repo.add_event(plant.id, "scan_added", diagnosis_id=diagnosis.id,
                            details={"treatment_stage": stage, "predicted_condition": diagnosis.predicted_condition})
        self.reassess(owner_id, plant.id)
        return link

    def unlink_scan(self, owner_id: UUID, plant_id: UUID, diagnosis_id: UUID) -> None:
        plant = self.require_plant(owner_id, plant_id)
        link = self.repo.link_for_diagnosis(diagnosis_id)
        if link is None or link.tracked_plant_id != plant.id:
            raise NotFoundError("That scan is not linked to this plant.")
        self.repo.delete(link)  # the diagnosis itself is kept
        self.repo.add_event(plant.id, "scan_removed", diagnosis_id=diagnosis_id)
        self.reassess(owner_id, plant.id)

    def scans(self, owner_id: UUID, plant_id: UUID) -> List[dict]:
        """Chronological scans with the measurements the recovery engine uses."""
        self.require_plant(owner_id, plant_id)
        pairs = self.repo.links_with_diagnoses(plant_id)
        segmentations = self.segmentation_repo.get_for_diagnoses([d.id for _, d in pairs])
        return [{"link": link, "diagnosis": diag, "segmentation": segmentations.get(diag.id)} for link, diag in pairs]

    def snapshots(self, scans: List[dict]) -> List[ScanSnapshot]:
        out = []
        for item in scans:
            d, seg = item["diagnosis"], item["segmentation"]
            usable_area = seg is not None and seg.status == "ok" and seg.affected_area_pct is not None
            out.append(ScanSnapshot(
                diagnosis_id=str(d.id), taken_at=_aware(d.diagnosed_at), condition=d.predicted_condition,
                is_healthy=(d.predicted_condition == "healthy") if d.predicted_condition else None,
                confidence=float(d.confidence_score) if d.confidence_score is not None else None,
                area_pct=float(seg.affected_area_pct) if usable_area else None,
                area_model=f"{seg.model_name}@{seg.model_version}" if usable_area else None,
                quality_issues=list((d.image_quality_json or {}).get("issues", [])),
                treatment_stage=item["link"].treatment_stage))
        return out

    # ------------------------------------------------------------------ assessment
    def reassess(self, owner_id: UUID, plant_id: UUID) -> RecoveryAssessmentModel:
        self.require_plant(owner_id, plant_id)
        result = assess(self.snapshots(self.scans(owner_id, plant_id)), self.rules)
        latest = self.repo.latest_assessment(plant_id)
        if latest and (latest.status, latest.limitations_json, latest.area_series_json,
                       str(latest.latest_diagnosis_id) if latest.latest_diagnosis_id else None) == \
                (result.status, result.limitations, result.area_series, result.latest_diagnosis_id):
            return latest  # unchanged — don't fill the timeline with duplicates
        row = self.repo.add(RecoveryAssessmentModel(
            tracked_plant_id=plant_id, status=result.status, method_version=result.method_version,
            baseline_diagnosis_id=UUID(result.baseline_diagnosis_id) if result.baseline_diagnosis_id else None,
            latest_diagnosis_id=UUID(result.latest_diagnosis_id) if result.latest_diagnosis_id else None,
            indicators_json=result.indicators, limitations_json=result.limitations,
            area_series_json=result.area_series, summary=result.summary,
            # Explicit microsecond timestamp: "latest assessment" is ordered by it, and a
            # coarse server clock could tie two assessments made in the same second.
            created_at=datetime.now(timezone.utc)))
        self.repo.add_event(plant_id, "assessment_updated", assessment_id=row.id, details={"status": row.status})
        return row

    def latest_assessment(self, owner_id: UUID, plant_id: UUID) -> RecoveryAssessmentModel:
        self.require_plant(owner_id, plant_id)
        return self.repo.latest_assessment(plant_id) or self.reassess(owner_id, plant_id)

    # ------------------------------------------------------------------ treatments
    def add_treatment(self, owner_id: UUID, plant_id: UUID, data: dict) -> TreatmentRecordModel:
        plant = self.require_plant(owner_id, plant_id)
        if data["category"] not in TREATMENT_CATEGORIES:
            raise ValidationError(f"category must be one of {TREATMENT_CATEGORIES}.")
        if data.get("follow_up_on") and data["follow_up_on"] < data["applied_on"]:
            raise ValidationError("follow_up_on can't be before applied_on.")
        row = self.repo.add(TreatmentRecordModel(tracked_plant_id=plant.id, **data))
        self.repo.add_event(plant.id, "treatment_recorded", treatment_record_id=row.id,
                            details={"name": row.name, "category": row.category})
        if row.follow_up_on:
            self.add_reminder(owner_id, plant.id, "treatment_follow_up", row.follow_up_on,
                              f"Follow up on: {row.name}", row.id)
        return row

    def delete_treatment(self, owner_id: UUID, plant_id: UUID, treatment_id: UUID) -> None:
        self.require_plant(owner_id, plant_id)
        row = self.repo.get_treatment(plant_id, treatment_id)
        if row is None:
            raise NotFoundError("Treatment record not found.")
        self.repo.delete(row)
        self.repo.add_event(plant_id, "treatment_deleted", details={"name": row.name})

    # ------------------------------------------------------------------ reminders
    def add_reminder(self, owner_id: UUID, plant_id: UUID, kind: str, due_on: date, note: Optional[str],
                     treatment_id: Optional[UUID] = None) -> FollowUpReminderModel:
        self.require_plant(owner_id, plant_id)
        if kind not in REMINDER_KINDS:
            raise ValidationError(f"kind must be one of {REMINDER_KINDS}.")
        if treatment_id and self.repo.get_treatment(plant_id, treatment_id) is None:
            raise NotFoundError("Treatment record not found.")
        row = self.repo.add(FollowUpReminderModel(tracked_plant_id=plant_id, kind=kind, due_on=due_on, note=note,
                                                  treatment_record_id=treatment_id))
        self.repo.add_event(plant_id, "reminder_created", reminder_id=row.id, details={"kind": kind, "due_on": due_on.isoformat()})
        return row

    def set_reminder_status(self, owner_id: UUID, plant_id: UUID, reminder_id: UUID, status: str) -> FollowUpReminderModel:
        self.require_plant(owner_id, plant_id)
        if status not in REMINDER_STATUSES:
            raise ValidationError(f"status must be one of {REMINDER_STATUSES}.")
        row = self.repo.get_reminder(plant_id, reminder_id)
        if row is None:
            raise NotFoundError("Reminder not found.")
        row.status = status
        row.completed_at = datetime.now(timezone.utc) if status == "completed" else None
        self.repo.add_event(plant_id, f"reminder_{status}", commit=False, reminder_id=row.id)
        self.repo.commit()
        return row


def reminder_state(row: FollowUpReminderModel, today: Optional[date] = None) -> str:
    """pending | overdue | completed | dismissed (overdue = pending and past due)."""
    today = today or date.today()
    if row.status == "pending" and row.due_on < today:
        return "overdue"
    return row.status


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


LIGHTING_DIFF_LUMA = 40.0   # mean-luma difference above which lighting is considered different
RESOLUTION_RATIO = 2.0      # pixel-count ratio above which resolutions are considered different


def compare_scans(first: dict, second: dict) -> dict:
    """Comparison of two scans of the same plant (dicts from RecoveryService.scans()).
    Raw pixel differences are never used as evidence; only measurements that are
    comparable (same segmentation model, valid area, acceptable images) are reported
    as a change. Every factor that weakens the comparison is listed."""
    a, b = first["diagnosis"], second["diagnosis"]
    qa, qb = a.image_quality_json or {}, b.image_quality_json or {}
    sa, sb = first["segmentation"], second["segmentation"]
    limitations = ["camera_angle_and_distance_not_verified"]
    checks = {}
    days = (_aware(b.diagnosed_at) - _aware(a.diagnosed_at)).total_seconds() / 86400
    checks["days_between"] = round(days, 1)
    if qa and qb:
        pixels_a, pixels_b = qa["width"] * qa["height"], qb["width"] * qb["height"]
        ratio = max(pixels_a, pixels_b) / max(1, min(pixels_a, pixels_b))
        checks["resolution_ratio"] = round(ratio, 2)
        if ratio > RESOLUTION_RATIO:
            limitations.append("different_resolution")
        checks["lighting_difference"] = round(abs(qa["mean_luma"] - qb["mean_luma"]), 1)
        if checks["lighting_difference"] > LIGHTING_DIFF_LUMA:
            limitations.append("different_lighting")
        if qa.get("issues") or qb.get("issues"):
            limitations.append("image_quality_issues")
    else:
        limitations.append("image_quality_not_recorded")

    area_change = None
    if sa is None or sb is None or sa.status != "ok" or sb.status != "ok":
        limitations.append("localization_unavailable")
    elif sa.affected_area_pct is None or sb.affected_area_pct is None:
        limitations.append("affected_area_not_measurable")
    elif (sa.model_name, sa.model_version) != (sb.model_name, sb.model_version):
        limitations.append("different_segmentation_models")
    elif {"blurry", "too_dark", "overexposed"} & set(qa.get("issues", []) + qb.get("issues", [])):
        limitations.append("quality_too_low_for_measurement")
    else:
        area_change = {"from": float(sa.affected_area_pct), "to": float(sb.affected_area_pct),
                       "change_pct_points": round(float(sb.affected_area_pct) - float(sa.affected_area_pct), 2),
                       "model": f"{sa.model_name}@{sa.model_version}"}
    if a.predicted_condition != b.predicted_condition:
        checks["classification_changed"] = {"from": a.predicted_condition, "to": b.predicted_condition}
    return {"checks": checks, "area_change": area_change, "limitations": sorted(set(limitations))}
