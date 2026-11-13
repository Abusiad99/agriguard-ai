"""Plant recovery monitoring API: ownership on every route, scan linking, follow-up
scans, treatments (user-recorded only), reminders, timeline, comparison, assessment."""
from __future__ import annotations

import io
from datetime import date, timedelta

import pytest
from PIL import Image

from tests.conftest import make_auth_header


def _image():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (70, 120, 50)).save(buf, format="JPEG")
    buf.seek(0)
    return ("leaf.jpg", buf, "image/jpeg")


def _scan(client, headers, **form):
    resp = client.post("/api/v1/scans", headers=headers, files={"image": _image()}, data=form)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture()
def owner(client):
    return make_auth_header(client, email="grower@example.com")


@pytest.fixture()
def intruder(client):
    return make_auth_header(client, email="intruder@example.com")


def _plant(client, headers, **body):
    resp = client.post("/api/v1/tracked-plants", headers=headers, json={"name": "Tomato row 3", "crop": "tomato", **body})
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestPlantsAndOwnership:
    def test_create_list_update(self, client, owner):
        plant = _plant(client, owner, latitude=10.5, longitude=20.5, notes="north field")
        assert plant["status"] == "active" and plant["scan_count"] == 0
        listing = client.get("/api/v1/tracked-plants", headers=owner).json()
        assert listing["total"] == 1 and listing["items"][0]["id"] == plant["id"]
        updated = client.patch(f"/api/v1/tracked-plants/{plant['id']}", headers=owner,
                               json={"name": "Tomato row 4", "status": "archived", "clear_location": True}).json()
        assert updated["name"] == "Tomato row 4" and updated["status"] == "archived" and updated["latitude"] is None

    def test_validation(self, client, owner):
        assert client.post("/api/v1/tracked-plants", headers=owner, json={"name": ""}).status_code == 400
        assert client.post("/api/v1/tracked-plants", headers=owner, json={"name": "x", "latitude": 10}).status_code == 400
        assert client.post("/api/v1/tracked-plants", headers=owner, json={"name": "x", "latitude": 99, "longitude": 1}).status_code == 400

    def test_requires_login(self, client):
        assert client.get("/api/v1/tracked-plants").status_code == 401

    def test_another_users_plant_is_invisible_everywhere(self, client, owner, intruder):
        plant = _plant(client, owner)
        pid = plant["id"]
        diagnosis = _scan(client, intruder)["diagnosis_id"]
        attempts = [
            ("get", f"/api/v1/tracked-plants/{pid}", None),
            ("patch", f"/api/v1/tracked-plants/{pid}", {"name": "mine now"}),
            ("post", f"/api/v1/tracked-plants/{pid}/scans", {"diagnosis_id": diagnosis}),
            ("get", f"/api/v1/tracked-plants/{pid}/timeline", None),
            ("get", f"/api/v1/tracked-plants/{pid}/assessment", None),
            ("get", f"/api/v1/tracked-plants/{pid}/compare", None),
            ("get", f"/api/v1/tracked-plants/{pid}/treatments", None),
            ("post", f"/api/v1/tracked-plants/{pid}/treatments", {"name": "x", "category": "organic", "applied_on": "2026-01-01"}),
            ("post", f"/api/v1/tracked-plants/{pid}/reminders", {"kind": "next_scan", "due_on": "2026-12-01"}),
        ]
        for method, url, body in attempts:
            resp = getattr(client, method)(url, headers=intruder, json=body) if body else getattr(client, method)(url, headers=intruder)
            assert resp.status_code == 404, (method, url, resp.status_code)
        assert client.get("/api/v1/tracked-plants", headers=intruder).json()["total"] == 0
        # a follow-up scan into someone else's plant is refused before anything is saved
        before = client.get("/api/v1/diagnoses", headers=intruder).json()["total"]
        resp = client.post("/api/v1/scans", headers=intruder, files={"image": _image()}, data={"tracked_plant_id": pid})
        assert resp.status_code == 404
        assert client.get("/api/v1/diagnoses", headers=intruder).json()["total"] == before

    def test_admin_viewer_sees_no_private_plant_or_owner_actions(self, client, db_session, owner):
        from app.infrastructure.db.models.user_model import UserModel

        diagnosis_id = _scan(client, owner)["diagnosis_id"]
        _plant(client, owner, initial_diagnosis_id=diagnosis_id)
        mine = client.get(f"/api/v1/diagnoses/{diagnosis_id}", headers=owner).json()
        assert mine["viewer_is_owner"] is True and mine["tracked_plant"]["name"] == "Tomato row 3"
        admin = make_auth_header(client, email="admin.viewer@example.com")
        db_session.query(UserModel).filter(UserModel.email == "admin.viewer@example.com").one().role = "admin"
        db_session.commit()
        theirs = client.get(f"/api/v1/diagnoses/{diagnosis_id}", headers=admin).json()
        assert theirs["viewer_is_owner"] is False and theirs["tracked_plant"] is None

    def test_cannot_link_someone_elses_diagnosis(self, client, owner, intruder):
        plant = _plant(client, owner)
        foreign = _scan(client, intruder)["diagnosis_id"]
        resp = client.post(f"/api/v1/tracked-plants/{plant['id']}/scans", headers=owner, json={"diagnosis_id": foreign})
        assert resp.status_code == 404


class TestScansAndAssessment:
    def test_follow_up_scans_timeline_and_honest_assessment(self, client, owner):
        first = _scan(client, owner)
        plant = _plant(client, owner, initial_diagnosis_id=first["diagnosis_id"])
        second = _scan(client, owner, tracked_plant_id=plant["id"], treatment_stage="after_treatment")
        assert second["tracked_plant"] == {"id": plant["id"], "name": plant["name"]}

        detail = client.get(f"/api/v1/tracked-plants/{plant['id']}", headers=owner).json()
        scans = {s["diagnosis_id"]: s for s in detail["scans"]}  # SQLite timestamps tie within a second
        assert set(scans) == {first["diagnosis_id"], second["diagnosis_id"]}
        assert scans[second["diagnosis_id"]]["treatment_stage"] == "after_treatment"
        # No segmentation model -> no measured area -> no improvement claim.
        assert detail["assessment"]["status"] == "inconclusive"
        assert "area_comparison_unavailable" in detail["assessment"]["limitations"]

        comparison = client.get(f"/api/v1/tracked-plants/{plant['id']}/compare", headers=owner).json()
        assert comparison["area_change"] is None
        assert {"camera_angle_and_distance_not_verified", "localization_unavailable"} <= set(comparison["limitations"])

        events = [e["event_type"] for e in client.get(f"/api/v1/tracked-plants/{plant['id']}/timeline", headers=owner).json()["items"]]
        assert {"plant_created", "scan_added", "assessment_updated"} <= set(events)
        # historical scans are preserved: both diagnoses are still individually readable
        for d in (first, second):
            assert client.get(f"/api/v1/diagnoses/{d['diagnosis_id']}", headers=owner).status_code == 200

    def test_a_scan_belongs_to_one_plant(self, client, owner):
        diagnosis = _scan(client, owner)["diagnosis_id"]
        a, b = _plant(client, owner), _plant(client, owner, name="other")
        assert client.post(f"/api/v1/tracked-plants/{a['id']}/scans", headers=owner, json={"diagnosis_id": diagnosis}).status_code == 201
        assert client.post(f"/api/v1/tracked-plants/{b['id']}/scans", headers=owner, json={"diagnosis_id": diagnosis}).status_code == 409
        assert client.delete(f"/api/v1/tracked-plants/{a['id']}/scans/{diagnosis}", headers=owner).status_code == 204
        assert client.get(f"/api/v1/diagnoses/{diagnosis}", headers=owner).status_code == 200  # diagnosis kept

    def test_simultaneous_links_of_one_scan_conflict_instead_of_a_server_error(self, client, owner, monkeypatch):
        """Two requests can both see "not linked yet" and both insert; the unique constraint
        on the scan rejects the second. That used to surface as an unhandled error (500)."""
        from app.infrastructure.repositories.ai_features_repository import SqlAlchemyRecoveryRepository

        diagnosis = _scan(client, owner)["diagnosis_id"]
        a, b = _plant(client, owner), _plant(client, owner, name="other")
        assert client.post(f"/api/v1/tracked-plants/{a['id']}/scans", headers=owner, json={"diagnosis_id": diagnosis}).status_code == 201

        real_lookup = SqlAlchemyRecoveryRepository.link_for_diagnosis
        calls = {"n": 0}

        def stale_once(self, diagnosis_id):  # the first read misses the link the "other" request just wrote
            calls["n"] += 1
            return None if calls["n"] == 1 else real_lookup(self, diagnosis_id)

        monkeypatch.setattr(SqlAlchemyRecoveryRepository, "link_for_diagnosis", stale_once)
        resp = client.post(f"/api/v1/tracked-plants/{b['id']}/scans", headers=owner, json={"diagnosis_id": diagnosis})
        assert resp.status_code == 409 and resp.json()["error"]["code"] == "CONFLICT"
        monkeypatch.undo()
        detail = client.get(f"/api/v1/tracked-plants/{a['id']}", headers=owner).json()
        assert [s["diagnosis_id"] for s in detail["scans"]] == [diagnosis]  # still linked to the first plant only

    def test_single_scan_is_insufficient_and_compare_needs_two(self, client, owner):
        plant = _plant(client, owner, initial_diagnosis_id=_scan(client, owner)["diagnosis_id"])
        assert client.get(f"/api/v1/tracked-plants/{plant['id']}/assessment", headers=owner).json()["status"] == "insufficient_data"
        assert client.get(f"/api/v1/tracked-plants/{plant['id']}/compare", headers=owner).status_code == 400

    def test_invalid_treatment_stage_rejected(self, client, owner):
        plant = _plant(client, owner)
        resp = client.post("/api/v1/scans", headers=owner, files={"image": _image()},
                           data={"tracked_plant_id": plant["id"], "treatment_stage": "whenever"})
        assert resp.status_code == 400


class TestTreatmentsAndReminders:
    def test_treatment_is_user_recorded_and_creates_follow_up(self, client, owner):
        plant = _plant(client, owner)
        follow_up = (date.today() + timedelta(days=7)).isoformat()
        resp = client.post(f"/api/v1/tracked-plants/{plant['id']}/treatments", headers=owner, json={
            "name": "Copper spray", "category": "chemical", "applied_on": date.today().isoformat(),
            "dosage_text": "as on label", "follow_up_on": follow_up})
        assert resp.status_code == 201
        treatment = resp.json()
        assert treatment["source"] == "user_recorded" and treatment["dosage_text"] == "as on label"
        reminders = client.get(f"/api/v1/tracked-plants/{plant['id']}/reminders", headers=owner).json()
        assert reminders[0]["kind"] == "treatment_follow_up" and reminders[0]["treatment_record_id"] == treatment["id"]
        bad = client.post(f"/api/v1/tracked-plants/{plant['id']}/treatments", headers=owner, json={
            "name": "x", "category": "chemical", "applied_on": "2026-05-10", "follow_up_on": "2026-05-01"})
        assert bad.status_code == 400
        assert client.post(f"/api/v1/tracked-plants/{plant['id']}/treatments", headers=owner, json={
            "name": "x", "category": "miracle", "applied_on": "2026-05-10"}).status_code == 400

    def test_overdue_and_completed_reminders(self, client, owner):
        plant = _plant(client, owner)
        past = client.post(f"/api/v1/tracked-plants/{plant['id']}/reminders", headers=owner,
                           json={"kind": "next_scan", "due_on": (date.today() - timedelta(days=3)).isoformat()}).json()
        future = client.post(f"/api/v1/tracked-plants/{plant['id']}/reminders", headers=owner,
                             json={"kind": "next_scan", "due_on": (date.today() + timedelta(days=3)).isoformat()}).json()
        assert past["state"] == "overdue" and future["state"] == "pending"
        overdue = client.get("/api/v1/tracked-plants/reminders?state=overdue", headers=owner).json()
        assert [r["id"] for r in overdue["items"]] == [past["id"]] and overdue["items"][0]["plant_name"] == plant["name"]
        done = client.patch(f"/api/v1/tracked-plants/{plant['id']}/reminders/{past['id']}", headers=owner,
                            json={"status": "completed"}).json()
        assert done["state"] == "completed" and done["completed_at"]
        assert client.get("/api/v1/tracked-plants/reminders?state=overdue", headers=owner).json()["items"] == []
