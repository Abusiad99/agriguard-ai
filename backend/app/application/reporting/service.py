"""ReportService — generates, stores, versions, renders and shares agricultural reports.

Pipeline for every report:
  collect evidence (database records + model registry; JSON-able, fingerprinted)
  -> build structured content (builders.py, pure)
  -> recommendations (recommendations.py, rule-based)
  -> narrative (narrative.py: LLM wording checked against the facts, or a template)
  -> validate_content (no number without a source, no unavailable fact without a reason)
  -> store an immutable version with its source references and data hash.
Regenerating creates a new version; older versions are kept. Media are stored as
storage keys and signed only when a report is read (owner/admin, or a valid share).
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ai import registry
from ai.outbreak import grid
from app.application.reporting import builders
from app.application.reporting.content import GENERATOR_VERSION, SCHEMA_VERSION, canonical_hash, validate_content
from app.application.reporting.i18n import LOCALES, day, t
from app.application.reporting.narrative import build_narrative, gemini_generator
from app.application.reporting.recommendations import (diagnosis_recommendations, load_rules,
                                                       outbreak_recommendations, plant_progress_recommendations)
from app.application.reporting.references import Citations, catalog_version
from app.application.services.outbreak_service import PREDICTION_FRESHNESS, OutbreakService, utc_today
from app.application.services.recovery_service import RecoveryService, reminder_state
from app.core.config import get_settings
from app.core.exceptions import AgriGuardError, AuthorizationError, ConflictError, NotFoundError, ValidationError
from app.core.media_urls import signed_media_url
from app.domain.entities.user import User, UserRole
from app.infrastructure.db.models.knowledge_base_model import DiseaseModel, PlantModel
from app.infrastructure.db.models.report_center_model import GeneratedReportModel, ReportShareModel
from app.infrastructure.repositories.report_center_repository import SqlAlchemyReportCenterRepository

REPORT_TYPES = ("diagnosis", "plant_progress", "outbreak_area")
_TYPE_CODE = {"diagnosis": "DX", "plant_progress": "PP", "outbreak_area": "OA"}


class ReportIntegrityError(AgriGuardError):
    code = "REPORT_INTEGRITY_ERROR"
    status_code = 500


def _iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    return value.isoformat() if isinstance(value, date) else value


def _f(value):
    return float(value) if value is not None else None


def reference(row) -> str:
    return f"AGR-{_TYPE_CODE[row.report_type]}-{str(row.id)[:8].upper()}-v{row.version}"


@dataclass
class ShareCreated:
    share: ReportShareModel
    token: str


class ReportService:
    def __init__(self, repo: SqlAlchemyReportCenterRepository, diagnosis_repo, disease_repo, treatment_repo,
                 segmentation_repo, recovery_service: Optional[RecoveryService], outbreak_service: Optional[OutbreakService],
                 storage, generator_factory: Callable[[], Optional[Callable[[str], str]]] = gemini_generator,
                 reference_service=None):
        self.repo, self.db = repo, repo.db
        self.reference_service = reference_service
        self.diagnosis_repo, self.disease_repo, self.treatment_repo = diagnosis_repo, disease_repo, treatment_repo
        self.segmentation_repo, self.recovery, self.outbreak = segmentation_repo, recovery_service, outbreak_service
        self.storage = storage
        self.generator_factory = generator_factory
        self.settings = get_settings()

    # =================================================================== generation
    def generate(self, user: User, report_type: str, locale: str, subject_id: Optional[UUID] = None,
                 options: Optional[dict] = None) -> GeneratedReportModel:
        if report_type not in REPORT_TYPES:
            raise ValidationError(f"type must be one of {', '.join(REPORT_TYPES)}.")
        if locale not in LOCALES:
            raise ValidationError("locale must be 'en' or 'ar'.")
        options = options or {}
        if report_type == "diagnosis":
            owner_id, subject, ev, sources = self._collect_diagnosis(user, subject_id)
            build, recommend = builders.build_diagnosis, diagnosis_recommendations
        elif report_type == "plant_progress":
            owner_id, subject, ev, sources = self._collect_plant(user, subject_id)
            build, recommend = builders.build_plant_progress, plant_progress_recommendations
        else:
            owner_id, subject, ev, sources = self._collect_outbreak(user, subject_id, options)
            build, recommend = builders.build_outbreak_area, outbreak_recommendations
        cites = Citations(locale, ev.get("kb_references"))
        content = build(ev, locale, cites)
        content["recommendations"] = recommend(ev, content, locale, cites)
        content["references"] = cites.to_list()  # recommendations may cite more sources
        sources += [{"kind": "reference", "table": "knowledge_references", "id": r["id"][3:]}
                    for r in content["references"] if r["origin"] == "knowledge_base"]

        narrative = build_narrative(content, locale, self._known_disease_names(), self.generator_factory())
        narrative["facts"] = [{"id": f["id"], "key": f["key"]} for f in narrative["facts"]]
        content["narrative"] = narrative
        content["schema"], content["generator"], content["locale"] = SCHEMA_VERSION, GENERATOR_VERSION, locale
        content["synthetic"] = any(m.get("synthetic") for m in content.get("methods", []))
        content["methods"].append({"id": "recommendation_rules", "name": t(locale, "m.recommendation_rules"), "kind": "rule",
                                   "version": ev["rules"]["rules_version"]})
        content["methods"].append({"id": "narrative", "name": t(locale, "m.narrative"),
                                   "kind": "llm_summary" if narrative["source"] == "llm" else "rule",
                                   "version": narrative.get("model") or "template-v2"})
        content["methods"].append({"id": "references", "name": t(locale, "m.references"), "kind": "reference",
                                   "version": catalog_version()})
        problems = validate_content(content)
        if problems:
            raise ReportIntegrityError("The report failed its integrity checks: " + "; ".join(problems[:5]))

        fields = dict(
            owner_id=owner_id, report_type=report_type, subject_id=subject, title=content["title"][:300], locale=locale,
            crop=(content.get("crop") or None), disease=(content.get("disease") or None),
            status_summary=(content.get("status") or {}).get("code"),
            period_start=date.fromisoformat(content["period"][0]) if content.get("period") else None,
            period_end=date.fromisoformat(content["period"][1]) if content.get("period") else None,
            schema_version=SCHEMA_VERSION, generator_version=GENERATOR_VERSION, content_json=content,
            sources_json=sources, data_hash=canonical_hash(ev), narrative_source=narrative["source"],
            narrative_model=narrative.get("model"), created_by=user.id)
        for attempt in (1, 2):
            previous = self.repo.latest_version(owner_id, report_type, subject)
            row = GeneratedReportModel(**fields, version=(previous.version + 1) if previous else 1,
                                       supersedes_id=previous.id if previous else None)
            try:
                return self.repo.add(row)
            except IntegrityError:
                # Two requests for the same subject (e.g. a double click) computed the same
                # next version; the unique (owner, type, subject, version) constraint kept
                # one. Number this one after it instead of failing with a server error.
                self.db.rollback()
                if attempt == 2:
                    raise ConflictError("Another report for this subject is being created. Please try again.")
        raise AssertionError("unreachable")  # pragma: no cover

    def regenerate(self, user: User, report_id: UUID, locale: Optional[str] = None) -> GeneratedReportModel:
        row = self.get(user, report_id)
        options, subject = {}, row.subject_id
        if row.report_type == "outbreak_area":
            # The stored subject id of an area report is derived from area + crop + disease;
            # regeneration needs the grid area itself.
            content = row.content_json
            subject = UUID(content["subject"]["area_id"])
            options = {"crop": content["subject"]["crop"], "disease": content["subject"]["disease"],
                       "date_from": content["subject"]["date_from"], "date_to": content["subject"]["date_to"]}
        return self.generate(user, row.report_type, locale or row.locale, subject, options)

    # ===================================================================== evidence
    def _classifier_card(self, class_keys: Optional[List[str]] = None):
        run_dir = self.settings.ai_artifacts_run_dir
        card = registry.describe("classification", Path(run_dir) if run_dir else None)
        out = {"name": card.name or "classifier", "version": card.version, "num_classes": len(card.classes) or None,
               "synthetic": bool((card.details or {}).get("synthetic")), "test": None}
        metrics_path = Path(card.run_dir) / "metrics.json" if card.run_dir else None
        if metrics_path and metrics_path.is_file():
            # Held-out TEST split results written by train.py (ai/training/metrics.py).
            import json

            try:
                m = json.loads(metrics_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                m = {}
            per_class = {str(k).lower(): v for k, v in (m.get("per_class") or {}).items() if isinstance(v, dict)}
            wanted = {k.lower() for k in class_keys or []}
            if m:
                out["test"] = {"accuracy": m.get("accuracy"),
                               "n_test": sum(int(v.get("support") or 0) for v in per_class.values()) or None,
                               "classes": {k: per_class[k] for k in sorted(wanted) if k in per_class},
                               "record": f"model_runs/{card.version}/metrics.json"}
        return out

    def _kb(self, disease_id) -> Tuple[Optional[dict], List[dict]]:
        if not disease_id:
            return None, []
        disease = self.disease_repo.get_by_id(disease_id)
        if disease is None:
            return None, []
        plant = self.db.get(PlantModel, disease.plant_id) if disease.plant_id else None
        kb = {"id": str(disease.id), "name": disease.name, "plant": plant.canonical_name if plant else None,
              "type": disease.disease_type, "description": disease.description,
              "symptoms": list(disease.symptoms or []), "causes": list(disease.causes or []),
              "transmission": disease.transmission_method, "recovery_probability": _f(disease.recovery_probability),
              "recovery_time": disease.estimated_recovery_time, "version": disease.version}
        treatments = [{"id": str(tr.id), "category": tr.category.value, "instructions": tr.instructions,
                       "safety_notes": tr.safety_notes, "citation": tr.source_citation,
                       "referral_only": tr.authority_referral_only, "displayable": tr.may_display_instructions(),
                       "version": tr.version}
                      for tr in self.treatment_repo.get_current_for_disease(disease.id)]
        return kb, treatments

    def _kb_references(self, kb: Optional[dict], treatments: List[dict]) -> List[dict]:
        if self.reference_service is None or not kb:
            return []
        return self.reference_service.for_report(kb, [tr["id"] for tr in treatments])

    def _alt_kb(self, alternatives: List[dict]) -> dict:
        """Knowledge-base symptoms of the classifier's alternatives, to tell them apart."""
        out = {}
        for p in alternatives:
            plant = self.db.execute(select(PlantModel).where(PlantModel.canonical_name == p.get("plant"))).scalar_one_or_none()
            row = self.disease_repo.get_current_by_plant_and_name(plant.id, p.get("condition")) if plant and p.get("condition") else None
            if row is not None:
                out[f"{p.get('plant')}___{p.get('condition')}"] = {"id": str(row.id), "name": row.name, "version": row.version,
                                                                   "symptoms": list(row.symptoms or [])}
        return out

    def _known_disease_names(self) -> List[str]:
        names = self.db.execute(select(DiseaseModel.name).distinct()).scalars()
        out = set()
        for n in names:
            if n:
                out.add(n)
                out.add(n.replace("_", " "))
        return sorted(out)

    def _collect_diagnosis(self, user: User, diagnosis_id: Optional[UUID]):
        if diagnosis_id is None:
            raise ValidationError("subject_id (the diagnosis id) is required.")
        d = self.diagnosis_repo.get_by_id(diagnosis_id)
        if d is None:
            raise NotFoundError("Diagnosis not found.")
        if d.user_id != user.id:
            # Reports land in the owner's archive, so only the owner creates them (admins can
            # still open existing reports).
            raise AuthorizationError("Only the owner of this diagnosis can create a report for it.")
        plant = self.db.get(PlantModel, d.plant_id) if d.plant_id else None
        kb, treatments = self._kb(d.disease_id)
        seg_row = self.segmentation_repo.get_for_diagnosis(d.id) if self.segmentation_repo else None
        seg = None
        if seg_row is not None:
            seg_card = registry.describe("segmentation")
            seg = {"id": str(seg_row.id), "status": seg_row.status, "model_name": seg_row.model_name,
                   "model_version": seg_row.model_version, "affected_pct": _f(seg_row.affected_area_pct),
                   "plant_pixels": seg_row.plant_pixels, "affected_pixels": seg_row.affected_pixels,
                   "reason": seg_row.area_unavailable_reason, "regions": seg_row.regions_json or [],
                   "class_pixels": seg_row.class_pixels_json or {}, "classes": seg_row.classes_json or [],
                   "area_basis": seg_row.area_basis, "mean_uncertainty": _f(seg_row.mean_uncertainty),
                   "mean_confidence": _f(seg_row.mean_confidence), "artifact_dir": seg_row.artifact_dir,
                   "synthetic": bool((seg_card.details or {}).get("synthetic")) and seg_card.version == seg_row.model_version}
        is_healthy = d.is_healthy() or d.predicted_condition == "healthy"
        w = d.weather_snapshot
        diag = {
            "id": str(d.id), "diagnosed_at": _iso(d.diagnosed_at), "plant_name": plant.canonical_name if plant else None,
            "predicted_condition": d.predicted_condition, "is_healthy": is_healthy, "confidence": _f(d.confidence_score),
            "low_confidence": bool(d.low_confidence_flag),
            "severity_level": d.severity_level.value if d.severity_level else None,
            "gradcam_area_pct": _f(d.affected_area_pct), "quality": d.image_quality, "top_predictions": d.top_predictions,
            "original_ref": d.original_image_ref, "heatmap_ref": d.heatmap_image_ref,
            "location_shared": d.location_lat is not None and d.location_lon is not None,
            "weather": {"temperature_c": _f(w.temperature_c), "humidity_pct": _f(w.humidity_pct),
                        "wind_speed_kmh": _f(w.wind_speed_kmh), "rain_probability_pct": _f(w.rain_probability_pct),
                        "retrieved_at": _iso(w.retrieved_at)} if w else None,
        }
        sources = [{"kind": "diagnosis", "table": "diagnoses", "id": str(d.id)}]
        if kb:
            sources.append({"kind": "knowledge_base", "table": "diseases", "id": kb["id"], "version": kb["version"]})
            sources += [{"kind": "knowledge_base", "table": "treatments", "id": tr["id"], "version": tr["version"]} for tr in treatments]
        if seg:
            sources.append({"kind": "segmentation", "table": "diagnosis_segmentations", "id": seg["id"]})
        rules = load_rules()
        ranked = d.top_predictions or []
        class_keys = [f"{plant.canonical_name if plant else None}___{d.predicted_condition}"] + \
                     [f"{p.get('plant')}___{p.get('condition')}" for p in ranked]
        alternatives = [p for p in ranked if not (p.get("condition") == d.predicted_condition
                                                  and p.get("plant") == (plant.canonical_name if plant else None))]
        ev = {"diagnosis": diag, "classifier": self._classifier_card(class_keys), "segmentation": seg, "kb_disease": kb,
              "kb_treatments": treatments, "kb_references": self._kb_references(kb, treatments),
              "alt_kb": self._alt_kb(alternatives), "tracked": self._tracked_context(d, int(rules["max_history_scans"])),
              "area": self._diagnosis_area(d, plant), "rules": rules}
        if ev["tracked"]:
            sources.append({"kind": "tracked_plant", "table": "tracked_plants", "id": ev["tracked"]["plant_id"]})
        return d.user_id, d.id, ev, sources

    def _tracked_context(self, d, max_history: int = 4) -> Optional[dict]:
        if self.recovery is None:
            return None
        repo = self.recovery.repo
        link = repo.link_for_diagnosis(d.id)
        plant = repo.get_owned_plant(link.tracked_plant_id, d.user_id) if link else None
        if plant is None:
            return None
        reminders = repo.list_reminders(plant.id)
        pending = sorted((r for r in reminders if r.status == "pending"), key=lambda r: r.due_on)
        latest = repo.latest_assessment(plant.id)
        pairs = repo.links_with_diagnoses(plant.id)
        before = [diag for _, diag in pairs if diag.id != d.id and _aware(diag.diagnosed_at) <= _aware(d.diagnosed_at)]
        segs = self.segmentation_repo.get_for_diagnoses([x.id for x in before]) if self.segmentation_repo and before else {}
        history = []
        for diag in before[-max_history:]:
            seg = segs.get(diag.id)
            ok = seg is not None and seg.status == "ok" and seg.affected_area_pct is not None
            history.append({"id": str(diag.id), "diagnosed_at": _iso(diag.diagnosed_at), "condition": diag.predicted_condition,
                            "confidence": _f(diag.confidence_score), "area_pct": _f(seg.affected_area_pct) if ok else None,
                            "area_model": f"{seg.model_name}@{seg.model_version}" if ok else None,
                            "original_ref": diag.original_image_ref,
                            "overlay_key": f"{seg.artifact_dir}/overlay.png" if ok and seg.artifact_dir else None})
        treatments = sorted(repo.list_treatments(plant.id), key=lambda x: x.applied_on, reverse=True)
        return {"plant_id": str(plant.id), "name": plant.name, "scans": len(pairs),
                "latest_status": latest.status if latest else None, "method_version": latest.method_version if latest else None,
                "assessment": {"status": latest.status, "method_version": latest.method_version,
                               "area_series": latest.area_series_json or []} if latest else None,
                "history": history, "treatments": len(treatments),
                "recent_treatments": [{"id": str(x.id), "name": x.name, "category": x.category, "applied_on": _iso(x.applied_on)}
                                      for x in treatments[:3]],
                "next_reminder": _iso(pending[0].due_on) if pending else None,
                "overdue": sum(1 for r in reminders if reminder_state(r) == "overdue")}

    def _diagnosis_area(self, d, plant) -> Optional[dict]:
        """Area context only when the owner shared the scan location (opt-in)."""
        if self.outbreak is None or d.location_lat is None or d.location_lon is None:
            return None
        cell = grid.cell_for(d.location_lat, d.location_lon, self.settings.outbreak_grid_resolution_deg)
        area = self.outbreak.repo.get_area_by_key(cell.key)
        if area is None:
            return None
        crop = plant.canonical_name if plant else None
        disease = None if d.is_healthy() else d.predicted_condition
        detail = self.outbreak.area_detail(area.id, crop, disease, 13)
        summary = detail.get("summary") or {"inspections": 0, "positives": 0, "positive_rate": None}
        fresh = [p for p in detail.get("predictions", []) if p.get("created_at")
                 and datetime.fromisoformat(p["created_at"]) >= datetime.now(timezone.utc) - PREDICTION_FRESHNESS]
        return {"area_id": str(area.id), "inspections": summary.get("inspections") or 0, "positives": summary.get("positives") or 0,
                "positive_rate": summary.get("positive_rate"), "prediction": fresh[0] if fresh else None}

    def _collect_plant(self, user: User, plant_id: Optional[UUID]):
        if self.recovery is None:
            raise ValidationError("Plant tracking is not available.")
        if plant_id is None:
            raise ValidationError("subject_id (the tracked plant id) is required.")
        plant = self.recovery.require_plant(user.id, plant_id)  # owner only; 404 for anyone else
        items = self.recovery.scans(user.id, plant_id)
        assessment = self.recovery.latest_assessment(user.id, plant_id)
        repo = self.recovery.repo
        scans = []
        for item in items:
            d, seg, link = item["diagnosis"], item["segmentation"], item["link"]
            ok = seg is not None and seg.status == "ok" and seg.affected_area_pct is not None
            quality = getattr(d, "image_quality_json", None) or {}
            scans.append({"id": str(d.id), "diagnosed_at": _iso(d.diagnosed_at), "condition": d.predicted_condition,
                          "is_healthy": d.predicted_condition == "healthy", "confidence": _f(d.confidence_score),
                          "low_confidence": bool(d.low_confidence_flag),
                          "severity_level": getattr(d.severity_level, "value", d.severity_level),
                          "quality_issues": list(quality.get("issues") or []),
                          "area_reason": None if ok else builders._area_reason(
                              {"status": seg.status, "reason": seg.area_unavailable_reason} if seg is not None else None),
                          "area_pct": _f(seg.affected_area_pct) if ok else None,
                          "area_model": f"{seg.model_name}@{seg.model_version}" if ok else None,
                          "stage": link.treatment_stage, "original_ref": d.original_image_ref,
                          "overlay_key": f"{seg.artifact_dir}/overlay.png" if ok and seg.artifact_dir else None,
                          "disease_id": str(d.disease_id) if d.disease_id else None})
        treatments = [{"id": str(tr.id), "name": tr.name, "category": tr.category, "applied_on": _iso(tr.applied_on),
                       "dosage_text": tr.dosage_text} for tr in repo.list_treatments(plant_id)]
        reminders = repo.list_reminders(plant_id)
        events, _ = repo.list_events(plant_id, 1, 200)
        kb, kb_treatments = self._kb(UUID(scans[-1]["disease_id"])) if scans and scans[-1]["disease_id"] else (None, [])
        from ai.recovery.engine import RecoveryRules

        pending = sorted((r for r in reminders if r.status == "pending"), key=lambda r: r.due_on)
        ev = {"plant": {"id": str(plant.id), "name": plant.name, "crop": plant.crop, "species": plant.species,
                        "created_at": _iso(plant.created_at)},
              "scans": scans,
              "assessment": {"id": str(assessment.id), "status": assessment.status, "method_version": assessment.method_version,
                             "limitations": assessment.limitations_json or [], "area_series": assessment.area_series_json or [],
                             "indicators": assessment.indicators_json or []},
              "treatments": treatments, "events": [{"occurred_at": _iso(e.occurred_at), "event_type": e.event_type}
                                                   for e in sorted(events, key=lambda e: e.occurred_at)],
              "reminders": [{"due_on": _iso(r.due_on), "state": reminder_state(r)} for r in reminders],
              "next_reminder": _iso(pending[0].due_on) if pending else None,
              "overdue_reminders": sum(1 for r in reminders if reminder_state(r) == "overdue"),
              "recovery_rules": {"stable_band_pct": RecoveryRules.load().stable_band_pct,
                                 "min_days_between": RecoveryRules.load().min_days_between,
                                 "blocking_quality_issues": RecoveryRules.load().blocking_quality_issues},
              "today": utc_today().isoformat(),
              "kb_disease": kb, "kb_treatments": kb_treatments, "kb_references": self._kb_references(kb, kb_treatments),
              "rules": load_rules(),
              "segmentation_synthetic": bool((registry.describe("segmentation").details or {}).get("synthetic"))}
        sources = ([{"kind": "tracked_plant", "table": "tracked_plants", "id": str(plant.id)},
                    {"kind": "assessment", "table": "recovery_assessments", "id": str(assessment.id)}]
                   + [{"kind": "diagnosis", "table": "diagnoses", "id": s["id"]} for s in scans]
                   + [{"kind": "user_record", "table": "treatment_records", "id": tr["id"]} for tr in treatments])
        return user.id, plant.id, ev, sources

    def _collect_outbreak(self, user: User, area_id: Optional[UUID], options: dict):
        if self.outbreak is None:
            raise ValidationError("Outbreak data is not available.")
        crop, disease = (options.get("crop") or "").strip().lower(), (options.get("disease") or "").strip().lower()
        if not crop or not disease:
            raise ValidationError("crop and disease are required for an area report.")
        repo = self.outbreak.repo
        if area_id is not None:
            area = repo.get_area(area_id)
            if area is None:
                raise NotFoundError("Area not found.")
        elif options.get("latitude") is not None and options.get("longitude") is not None:
            try:
                area = repo.get_or_create_area(grid.cell_for(options["latitude"], options["longitude"],
                                                             self.settings.outbreak_grid_resolution_deg))
            except (TypeError, ValueError) as exc:
                raise ValidationError(str(exc) or "invalid coordinates")
            repo.db.commit()
        else:
            raise ValidationError("subject_id (area id) or latitude/longitude is required.")
        date_to = _to_date(options.get("date_to")) or utc_today()
        date_from = _to_date(options.get("date_from")) or date_to - timedelta(days=90)
        if date_from > date_to or (date_to - date_from).days > 3 * 366:
            raise ValidationError("The period must be at most 3 years and start before it ends.")
        horizon = int(options.get("horizon_days") or 7)
        rules = load_rules()
        detail = self.outbreak.area_detail(area.id, crop, disease, 26, date_from, date_to)
        last_year = self.outbreak.area_detail(area.id, crop, disease, 26, date_from - timedelta(days=365),
                                              date_to - timedelta(days=365)).get("summary")
        res, radius = self.settings.outbreak_grid_resolution_deg, int(rules["region_radius_cells"])
        cell = grid.cell_from_key(area.grid_key)
        south, west = cell.lat_index * res - radius * res, cell.lon_index * res - radius * res
        north, east = (cell.lat_index + 1) * res + radius * res, (cell.lon_index + 1) * res + radius * res
        bbox = (max(-180.0, west), max(-90.0, south), min(180.0, east), min(90.0, north))
        region = self.outbreak.map_layer(crop, disease, date_from, date_to, bbox, horizon, 1, 500)
        own = next((c for c in region["cells"] if c["area"]["id"] == str(area.id)), None)
        prediction = None
        if own and own.get("prediction"):
            prediction = self.outbreak.get_prediction(UUID(own["prediction"]["prediction_id"]))
        plant = self.db.execute(select(PlantModel).where(PlantModel.canonical_name == crop)).scalar_one_or_none()
        disease_row = self.disease_repo.get_current_by_plant_and_name(plant.id, disease) if plant else None
        kb, kb_treatments = self._kb(disease_row.id) if disease_row else (None, [])
        summary = detail.get("summary")
        inspections = (summary or {}).get("inspections") or 0
        model_card = registry.describe("outbreak")
        ev = {"area": {"id": str(area.id), "grid_key": area.grid_key, "bounds": detail["area"]["bounds"]},
              "crop": crop, "disease": disease, "date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
              "summary": summary, "trend": detail.get("trend") or [],
              "last_year": {"inspections": (last_year or {}).get("inspections") or 0, "positives": (last_year or {}).get("positives") or 0},
              "weather": detail["weather"]["days"], "suitability": detail.get("suitability") or [],
              "region": {"cells": region["cells"], "hidden_for_privacy": region.get("hidden_for_privacy", 0)},
              "prediction": prediction, "kb_disease": kb, "kb_treatments": kb_treatments,
              "model_card": {"name": model_card.name, "version": model_card.version, "details": model_card.details or {},
                             "metrics": model_card.metrics or {}} if model_card.version else None,
              "data_gap": inspections < self.settings.outbreak_min_local_inspections,
              "privacy": region["privacy"], "rules": rules,
              "model_synthetic": bool((model_card.details or {}).get("synthetic"))}
        sources = [{"kind": "area", "table": "geo_areas", "id": str(area.id)},
                   {"kind": "observations", "table": "disease_observations", "id": f"{crop}/{disease}/{date_from}..{date_to}"}]
        if prediction:
            sources.append({"kind": "prediction", "table": "outbreak_predictions", "id": prediction["prediction_id"]})
        # The area itself is aggregate, public-to-users data: the report belongs to whoever asked for it.
        subject = UUID(hashlib.sha256(f"{area.id}|{crop}|{disease}".encode()).hexdigest()[:32])
        return user.id, subject, ev, sources

    # ======================================================================= access
    def get(self, user: User, report_id: UUID) -> GeneratedReportModel:
        row = self.repo.get(report_id)
        if row is None or (row.owner_id != user.id and user.role != UserRole.ADMIN):
            raise NotFoundError("Report not found.")  # 404 for other users' reports: don't reveal they exist
        return row

    def list(self, user: User, **filters):
        return self.repo.list(user.id, **filters)

    def versions(self, user: User, report_id: UUID) -> List[GeneratedReportModel]:
        row = self.get(user, report_id)
        return self.repo.versions(row.owner_id, row.report_type, row.subject_id)

    def to_public(self, row: GeneratedReportModel, shared: bool = False, share_expires: Optional[datetime] = None) -> dict:
        """The report as served: media keys replaced by short-lived signed URLs; internal
        record ids left out of shared views."""
        import copy

        content = copy.deepcopy(row.content_json)
        ttl = self.settings.media_url_ttl_seconds
        if share_expires is not None:
            ttl = max(60, min(ttl, int((_aware(share_expires) - datetime.now(timezone.utc)).total_seconds())))
        for m in content.get("media", []):
            key = m.pop("storage_key", None)
            m["url"] = signed_media_url(key, ttl_seconds=ttl) if key else None
        if shared:
            _scrub_for_share(content)
        out = {"id": str(row.id), "reference": reference(row), "type": row.report_type, "version": row.version,
               "title": row.title, "locale": row.locale, "status": row.status_summary, "crop": row.crop,
               "disease": row.disease, "created_at": _iso(row.created_at),
               "generated_display": day(row.created_at, row.locale), "schema_version": row.schema_version,
               "generator_version": row.generator_version, "data_hash": row.data_hash,
               "narrative_source": row.narrative_source, "narrative_model": row.narrative_model,
               "synthetic": bool(content.get("synthetic")), "content": content}
        if not shared:
            out.update({"subject_id": str(row.subject_id), "sources": row.sources_json,
                        "supersedes_id": str(row.supersedes_id) if row.supersedes_id else None})
        return out

    # ===================================================================== exports
    def pdf_path(self, row: GeneratedReportModel) -> Path:
        """Render once per version (reports are immutable) and cache in private storage."""
        from app.infrastructure.reporting.report_pdf import RENDERER_VERSION, region_map_png, render_report_pdf

        key = f"reports/generated/{row.id}-{row.locale}-{RENDERER_VERSION}.pdf"
        path = self.storage.resolve_path(key)
        if path.is_file():
            return path
        public = self.to_public(row)
        public["sources"] = row.sources_json
        content = row.content_json
        public["content"] = content  # the stored content keeps the media storage keys the renderer embeds
        if content.get("map"):
            public["region_map_png"] = region_map_png(content["map"]["cells"], content["map"]["selected"])

        def resolve(storage_key: str) -> Optional[Path]:
            try:
                p = self.storage.resolve_path(storage_key)
            except ValueError:
                return None
            return p if p.is_file() else None

        data = render_report_pdf(public, resolve)
        self.storage.save_bytes(data, key)
        refs = dict(row.pdf_refs_json or {})
        refs[row.locale] = key
        row.pdf_refs_json = refs
        self.repo.save(row)
        return path

    def map_png(self, row: GeneratedReportModel) -> bytes:
        from app.infrastructure.reporting.report_pdf import region_map_png

        content = row.content_json
        if not content.get("map"):
            raise NotFoundError("This report has no map.")
        return region_map_png(content["map"]["cells"], content["map"]["selected"])

    # ====================================================================== shares
    def create_share(self, user: User, report_id: UUID, expires_in_days: int) -> ShareCreated:
        row = self.get(user, report_id)
        if row.owner_id != user.id:
            raise AuthorizationError("Only the report's owner can share it.")
        if not 1 <= expires_in_days <= self.settings.report_share_max_days:
            raise ValidationError(f"expires_in_days must be between 1 and {self.settings.report_share_max_days}.")
        token = secrets.token_urlsafe(32)
        share = ReportShareModel(report_id=row.id, token_hash=_hash(token), created_by=user.id,
                                 expires_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days))
        return ShareCreated(self.repo.add(share), token)

    def list_shares(self, user: User, report_id: UUID) -> List[ReportShareModel]:
        row = self.get(user, report_id)
        return self.repo.shares(row.id)

    def revoke_share(self, user: User, report_id: UUID, share_id: UUID) -> ReportShareModel:
        row = self.get(user, report_id)
        if row.owner_id != user.id:
            raise AuthorizationError("Only the report's owner can manage its links.")
        share = self.repo.get_share(row.id, share_id)
        if share is None:
            raise NotFoundError("Share link not found.")
        if share.revoked_at is None:
            share.revoked_at = datetime.now(timezone.utc)
            self.repo.save(share)
        return share

    def open_share(self, token: str) -> Tuple[GeneratedReportModel, ReportShareModel]:
        share = self.repo.share_by_token_hash(_hash(token)) if token and len(token) <= 100 else None
        if share is None or share.revoked_at is not None or _aware(share.expires_at) <= datetime.now(timezone.utc):
            raise NotFoundError("This report link is invalid, expired or revoked.")
        row = self.repo.get(share.report_id)
        if row is None:
            raise NotFoundError("This report link is invalid, expired or revoked.")
        share.access_count = (share.access_count or 0) + 1
        share.last_accessed_at = datetime.now(timezone.utc)
        self.repo.save(share)
        return row, share


def _scrub_for_share(content: dict) -> None:
    """Shared copies carry no internal record ids: provenance records, table-row ids,
    subject ids and map-cell ids are removed or replaced with neutral ones. Reference ids
    (public sources) and the values themselves are kept."""
    def walk(node):
        if isinstance(node, dict):
            prov = node.get("provenance")
            if isinstance(prov, dict):
                prov.pop("record", None)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(content)
    subject = content.get("subject") or {}
    for key in [k for k in subject if k.endswith("_id") or k == "region_cells"]:
        subject.pop(key)
    for sec in content.get("sections", []):
        sec["facts"] = [f for f in sec.get("facts", []) if not str(f.get("key", "")).endswith("_id")]  # e.g. the scan id
        for i, row in enumerate(sec.get("rows") or []):
            row["id"] = f"row-{i + 1}"
    for cell in (content.get("map") or {}).get("cells", []):
        area = cell.get("area") or {}
        area["id"] = area.get("grid_key") or area.get("id")


def share_state(share: ReportShareModel) -> str:
    if share.revoked_at is not None:
        return "revoked"
    return "expired" if _aware(share.expires_at) <= datetime.now(timezone.utc) else "active"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _to_date(value) -> Optional[date]:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ValidationError("Dates must be YYYY-MM-DD.")
