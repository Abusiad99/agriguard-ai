"""
Load outbreak observations into the application database (for the risk map and for
prediction-time history features).

    python -m app.tools.outbreak_data import   [--dataset ../datasets/outbreak]
    python -m app.tools.outbreak_data backfill

import    Validates datasets/outbreak/raw/observations.csv and inserts every row as a
          `dataset` observation in its grid cell. Rows from a previous import of the same
          dataset version are replaced (re-running is idempotent); other data is untouched.
backfill  Records an observation for existing scans whose owner attached a location
          (the same rule new scans follow). Scans without a location are never used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from sqlalchemy import delete, select

from app.application.services.outbreak_service import OutbreakService
from app.core.config import get_settings
from app.infrastructure.db.models.ai_features_model import DiseaseObservationModel
from app.infrastructure.db.models.diagnosis_model import DiagnosisModel
from app.infrastructure.db.models.knowledge_base_model import PlantModel
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.external import ai_pipeline_client  # noqa: F401  (repo-root `ai` on sys.path)
from app.infrastructure.external.model_clients import OutbreakModelClient
from app.infrastructure.repositories.ai_features_repository import SqlAlchemyOutbreakRepository
from app.infrastructure.repositories.diagnosis_repository import SqlAlchemyDiagnosisRepository

from ai.outbreak import grid
from ai.outbreak.schema import OBSERVATIONS
from ai.outbreak.validate import default_dataset_root, read_table, validate_dataset

settings = get_settings()


def import_observations(dataset_root: Path) -> dict:
    report = validate_dataset(dataset_root)
    if not report["summary"]["ready_for_preprocessing"]:
        raise SystemExit(f"Validation failed ({report['summary']['errors']} errors); see "
                         f"{Path(dataset_root) / 'reports' / 'validation_summary.md'}")
    source = Path(dataset_root) / "raw" / OBSERVATIONS.file
    version = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    rows = read_table(source, OBSERVATIONS, [])
    with SessionLocal() as db:
        repo = SqlAlchemyOutbreakRepository(db)
        removed = db.execute(delete(DiseaseObservationModel).where(
            DiseaseObservationModel.source == "dataset", DiseaseObservationModel.dataset_version == version)).rowcount
        for _, r in rows:
            area = repo.get_or_create_area(grid.cell_for(r["latitude"], r["longitude"], settings.outbreak_grid_resolution_deg))
            inspected = r.get("inspected_count") or 1
            positives = r["positive_count"] if r.get("positive_count") is not None else (inspected if r["is_positive"] else 0)
            repo.add_observation(DiseaseObservationModel(
                area_id=area.id, source="dataset", dataset_version=version, crop=r["crop"], disease=r["disease"],
                is_positive=r["is_positive"], inspected_count=inspected, positive_count=positives,
                observed_on=r["observed_on"]), commit=False)
        db.commit()
    return {"dataset_version": version, "imported": len(rows), "replaced": removed or 0}


def backfill() -> dict:
    with SessionLocal() as db:
        service = OutbreakService(SqlAlchemyOutbreakRepository(db), OutbreakModelClient(), weather=None)
        diagnoses = SqlAlchemyDiagnosisRepository(db)
        located = db.execute(select(DiagnosisModel.id, PlantModel.canonical_name)
                             .join(PlantModel, PlantModel.id == DiagnosisModel.plant_id)
                             .where(DiagnosisModel.location_lat.isnot(None))).all()
        added = sum(1 for diagnosis_id, crop in located
                    if service.record_scan_observation(diagnoses.get_by_id(diagnosis_id), crop) is not None)
    return {"located_scans": len(located), "observations_added": added}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Outbreak observation data tools")
    parser.add_argument("action", choices=["import", "backfill"])
    parser.add_argument("--dataset", type=Path, default=default_dataset_root())
    args = parser.parse_args(argv)
    result = import_observations(args.dataset) if args.action == "import" else backfill()
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
