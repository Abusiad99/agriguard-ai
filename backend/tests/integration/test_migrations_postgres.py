"""
Alembic migrations against a real PostgreSQL database (0001 -> 0002 -> 0003, and
back): schema DDL, ENUM types, the dashboard materialized view, and rows that existed
before 0003 added diagnoses.predicted_condition.

REQUIRES INFRASTRUCTURE: runs only when AGRIGUARD_TEST_DATABASE_URL points at a
throwaway PostgreSQL database whose name ends in "_test" (enforced in conftest.py) —
the public schema of that database is dropped and recreated. Skipped otherwise, since
these migrations use PostgreSQL-only features (ENUM types, JSONB, materialized views,
pgcrypto) that SQLite cannot run.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from tests.conftest import TEST_DATABASE_URL

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL.startswith("postgresql"),
    reason="needs AGRIGUARD_TEST_DATABASE_URL pointing at a PostgreSQL *_test database",
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


def _alembic(*args: str) -> None:
    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL,
           "PYTHONPATH": os.pathsep.join([str(REPO_ROOT), str(BACKEND_DIR)])}
    result = subprocess.run([sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
                            cwd=BACKEND_DIR, env=env, capture_output=True, text=True)
    assert result.returncode == 0, f"alembic {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}"


def _reset_schema(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


def _diagnosis_columns(engine) -> dict:
    return {c["name"]: c for c in inspect(engine).get_columns("diagnoses")}


def _dashboard_view(conn, user_id) -> tuple:
    conn.execute(text("REFRESH MATERIALIZED VIEW mv_dashboard_monthly_stats"))
    return conn.execute(
        text("SELECT SUM(total_scans), SUM(healthy_count), SUM(diseased_count) "
             "FROM mv_dashboard_monthly_stats WHERE user_id = :u"), {"u": user_id},
    ).one()


@pytest.fixture()
def pg_engine():
    engine = create_engine(TEST_DATABASE_URL)
    _reset_schema(engine)
    yield engine
    _reset_schema(engine)
    engine.dispose()


def test_0003_upgrade_downgrade_round_trip_with_existing_rows(pg_engine):
    # --- Database as it was before this branch: migrated to 0002, with scan history.
    _alembic("upgrade", "0002")
    assert "predicted_condition" not in _diagnosis_columns(pg_engine)

    user_id, plant_id, legacy_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with pg_engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, email, password_hash, full_name) "
                          "VALUES (:id, 'legacy@example.com', 'h', 'Legacy User')"), {"id": user_id})
        conn.execute(text("INSERT INTO plants (id, canonical_name) VALUES (:id, 'tomato')"), {"id": plant_id})
        conn.execute(text("INSERT INTO diagnoses (id, user_id, plant_id, confidence_score, severity_level, "
                          "original_image_ref) VALUES (:id, :u, :p, 88.5, 'mild', 'scans/legacy.jpg')"),
                     {"id": legacy_id, "u": user_id, "p": plant_id})

    # --- Upgrade to 0003: nullable column added, existing rows untouched and NULL.
    _alembic("upgrade", "0003")
    column = _diagnosis_columns(pg_engine)["predicted_condition"]
    assert column["nullable"] is True
    assert column["default"] is None
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT predicted_condition FROM diagnoses WHERE id = :id"),
                            {"id": legacy_id}).scalar() is None
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0003"

    # --- The current application (which expects the head schema) reads the legacy row
    #     and writes the new column through its own repository, on the ENUM-typed schema.
    _alembic("upgrade", "head")
    from app.domain.entities.diagnosis import Diagnosis
    from app.infrastructure.repositories.diagnosis_repository import SqlAlchemyDiagnosisRepository

    session = sessionmaker(bind=pg_engine, expire_on_commit=False)()
    try:
        repo = SqlAlchemyDiagnosisRepository(session)
        legacy = repo.get_by_id(legacy_id)
        assert legacy.predicted_condition is None
        assert legacy.is_healthy() is True  # pre-0003 rows keep the old meaning

        created = repo.create(Diagnosis(
            id=None, user_id=user_id, plant_id=plant_id, disease_id=None, confidence_score=93.0,
            severity_level=None, affected_area_pct=None, healthy_area_pct=None,
            original_image_ref="scans/new.jpg", predicted_condition="late_blight",
        ))
        assert repo.get_by_id(created.id).predicted_condition == "late_blight"
        repo.create(Diagnosis(
            id=None, user_id=user_id, plant_id=plant_id, disease_id=None, confidence_score=97.0,
            severity_level=None, affected_area_pct=0.0, healthy_area_pct=100.0,
            original_image_ref="scans/healthy.jpg", predicted_condition="healthy",
        ))

        summary = repo.dashboard_summary(user_id=user_id)
        assert (summary["total_scans"], summary["healthy_count"], summary["diseased_count"]) == (3, 2, 1)
        assert [m["scan_count"] for m in summary["monthly_trend"]] == [3]  # to_char path on PostgreSQL
    finally:
        session.close()

    # --- The rebuilt materialized view applies the same rule as the repository.
    with pg_engine.begin() as conn:
        assert tuple(int(v) for v in _dashboard_view(conn, user_id)) == (3, 2, 1)

    # --- Downgrade all the way to 0002 (through 0006..0003): column dropped, original
    #     view restored, rows kept.
    _alembic("downgrade", "0002")
    assert "predicted_condition" not in _diagnosis_columns(pg_engine)
    with pg_engine.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM diagnoses")).scalar() == 3
        # Old rule: every NULL disease_id counts as healthy (the bug 0003 fixes).
        assert tuple(int(v) for v in _dashboard_view(conn, user_id)) == (3, 3, 0)

    # --- Re-upgrade works after a downgrade.
    _alembic("upgrade", "0003")
    assert "predicted_condition" in _diagnosis_columns(pg_engine)


def test_ai_feature_report_and_reference_migrations_0004_to_0008(pg_engine):
    from sqlalchemy.exc import IntegrityError

    _alembic("upgrade", "0003")
    user_id, plant_id, diag_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with pg_engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, email, password_hash, full_name) VALUES (:id, 'ai@example.com', 'h', 'AI')"), {"id": user_id})
        conn.execute(text("INSERT INTO plants (id, canonical_name) VALUES (:id, 'tomato')"), {"id": plant_id})
        conn.execute(text("INSERT INTO diagnoses (id, user_id, plant_id, confidence_score, original_image_ref, predicted_condition) "
                          "VALUES (:id, :u, :p, 90, 'scans/a.jpg', 'late_blight')"), {"id": diag_id, "u": user_id, "p": plant_id})

    _alembic("upgrade", "head")
    tables = set(inspect(pg_engine).get_table_names())
    assert {"diagnosis_segmentations", "tracked_plants", "tracked_plant_scans", "treatment_records", "follow_up_reminders",
            "recovery_assessments", "plant_timeline_events", "geo_areas", "disease_observations",
            "weather_observations", "outbreak_predictions"} <= tables
    assert "image_quality_json" in _diagnosis_columns(pg_engine)
    assert {"generated_reports", "report_shares"} <= tables and "top_predictions_json" in _diagnosis_columns(pg_engine)
    assert {"knowledge_references", "knowledge_reference_claims"} <= tables
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0008"
        assert conn.execute(text("SELECT image_quality_json FROM diagnoses WHERE id = :id"), {"id": diag_id}).scalar() is None

    # Constraints guard the invariants the services rely on.
    bad_rows = [
        "INSERT INTO diagnosis_segmentations (diagnosis_id, status, affected_area_pct) VALUES (:d, 'ok', 40)",  # % without denominator
        "INSERT INTO tracked_plants (owner_id, name, location_lat) VALUES (:u, 'x', 10)",                      # lat without lon
        "INSERT INTO treatment_records (tracked_plant_id, name, category, applied_on) VALUES (gen_random_uuid(), 'x', 'magic', now())",
        # reports: unknown type, unknown narrative source
        "INSERT INTO generated_reports (owner_id, report_type, subject_id, version, title, locale, schema_version, generator_version, "
        "content_json, sources_json, data_hash, narrative_source) VALUES (:u, 'magic', gen_random_uuid(), 1, 't', 'en', 's', 'g', '{}', '[]', 'h', 'template')",
        "INSERT INTO generated_reports (owner_id, report_type, subject_id, version, title, locale, schema_version, generator_version, "
        "content_json, sources_json, data_hash, narrative_source) VALUES (:u, 'diagnosis', gen_random_uuid(), 1, 't', 'en', 's', 'g', '{}', '[]', 'h', 'free_text')",
        # references: non-http URL, unknown source type, a claim attached to nothing
        "INSERT INTO knowledge_references (title, url, source_type) VALUES ('t', 'ftp://x', 'peer_reviewed')",
        "INSERT INTO knowledge_references (title, url, source_type) VALUES ('t', 'https://x.test/a', 'a_blog')",
        "INSERT INTO knowledge_reference_claims (reference_id, subject_type, claim) "
        "SELECT gen_random_uuid(), 'disease', 'c' WHERE :u IS NOT NULL",
    ]
    for sql in bad_rows:
        with pytest.raises(IntegrityError):
            with pg_engine.begin() as conn:
                conn.execute(text(sql), {"d": diag_id, "u": user_id})

    # The application writes and reads every new table through its own repositories.
    from datetime import date as _date

    from ai.outbreak import grid
    from app.infrastructure.db.models.ai_features_model import (DiagnosisSegmentationModel, DiseaseObservationModel,
                                                                TrackedPlantModel, TrackedPlantScanModel)
    from app.infrastructure.repositories.ai_features_repository import (SqlAlchemyOutbreakRepository,
                                                                        SqlAlchemyRecoveryRepository,
                                                                        SqlAlchemySegmentationRepository)
    session = sessionmaker(bind=pg_engine, expire_on_commit=False)()
    try:
        SqlAlchemySegmentationRepository(session).save(DiagnosisSegmentationModel(
            diagnosis_id=diag_id, status="ok", affected_area_pct=12.5, plant_pixels=800, affected_pixels=100,
            regions_json=[{"label": "lesion", "pixels": 100}], classes_json=[{"id": 0, "name": "background"}]))
        recovery = SqlAlchemyRecoveryRepository(session)
        plant = recovery.add(TrackedPlantModel(owner_id=user_id, name="Row 1", crop="tomato"))
        recovery.add(TrackedPlantScanModel(tracked_plant_id=plant.id, diagnosis_id=diag_id))
        assert recovery.plant_summaries([plant.id])[plant.id]["scan_count"] == 1
        outbreak = SqlAlchemyOutbreakRepository(session)
        area = outbreak.get_or_create_area(grid.cell_for(10.3, 20.4))
        outbreak.add_observation(DiseaseObservationModel(area_id=area.id, source="app_scan", diagnosis_id=diag_id, crop="tomato",
                                                         disease="late_blight", is_positive=True, positive_count=1,
                                                         observed_on=_date.today()))
        rows, total = outbreak.aggregate("tomato", "late_blight", _date(2000, 1, 1), _date.today(), None, 1, 10)
        assert total == 1 and rows[0].app_positives == 1 and rows[0].app_contributors == 1
        assert SqlAlchemySegmentationRepository(session).get_for_diagnosis(diag_id).regions_json[0]["pixels"] == 100
        from app.infrastructure.db.models.knowledge_reference_model import KnowledgeReferenceClaimModel, KnowledgeReferenceModel
        from app.infrastructure.repositories.knowledge_reference_repository import SqlAlchemyKnowledgeReferenceRepository
        refs = SqlAlchemyKnowledgeReferenceRepository(session)
        ref = refs.add(KnowledgeReferenceModel(title="Synthetic test source", url="https://example.test/source",
                                               source_type="university_extension"))
        refs.add(KnowledgeReferenceClaimModel(reference_id=ref.id, subject_type="disease", subject_key="tomato/late_blight",
                                              claim="synthetic claim"))
        assert [c.claim for c in refs.claims_for([("disease", "tomato/late_blight", None)])] == ["synthetic claim"]
    finally:
        session.close()

    # Downgrading 0008 removes only the reference tables.
    _alembic("downgrade", "0007")
    tables = set(inspect(pg_engine).get_table_names())
    assert not {"knowledge_references", "knowledge_reference_claims"} & tables and "generated_reports" in tables

    # Downgrading to 0003 removes only what 0004-0008 added; existing diagnoses stay.
    _alembic("downgrade", "0003")
    tables = set(inspect(pg_engine).get_table_names())
    assert not {"diagnosis_segmentations", "tracked_plants", "geo_areas", "outbreak_predictions",
                "generated_reports", "report_shares", "knowledge_references"} & tables
    assert "top_predictions_json" not in _diagnosis_columns(pg_engine)
    assert "image_quality_json" not in _diagnosis_columns(pg_engine)
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT predicted_condition FROM diagnoses WHERE id = :id"), {"id": diag_id}).scalar() == "late_blight"
    _alembic("upgrade", "head")
