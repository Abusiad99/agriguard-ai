"""Plant profiles, observations, notes, follow-up answers, comparison — and ownership
enforcement on every endpoint (insecure-direct-object-reference checks)."""
from __future__ import annotations

import io

from tests.conftest import make_auth_header, make_leaf_like_image_bytes


def _img(seed=0):
    return ("leaf.jpg", io.BytesIO(make_leaf_like_image_bytes(seed=seed)), "image/jpeg")


def _create_plant(client, headers, **extra):
    body = {"name": "Tomato row 3", **extra}
    resp = client.post("/api/v1/plants", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestPlantProfiles:
    def test_crud_with_optional_fields(self, client):
        h = make_auth_header(client, email="grower@example.com")
        p = _create_plant(client, h, crop_type="Tomato", growing_environment="greenhouse")
        assert p["crop_type"] == "tomato" and p["variety"] is None and p["observation_count"] == 0

        listed = client.get("/api/v1/plants", headers=h).json()
        assert listed["total"] == 1 and listed["items"][0]["id"] == p["id"]

        upd = client.patch(f"/api/v1/plants/{p['id']}", headers=h, json={"variety": "Roma"}).json()
        assert upd["variety"] == "Roma" and upd["name"] == "Tomato row 3"

        assert client.delete(f"/api/v1/plants/{p['id']}", headers=h).status_code == 204
        assert client.get("/api/v1/plants", headers=h).json()["total"] == 0
        assert client.get("/api/v1/plants?include_archived=true", headers=h).json()["total"] == 1

    def test_validation(self, client):
        h = make_auth_header(client, email="val@example.com")
        assert client.post("/api/v1/plants", headers=h, json={"name": ""}).status_code in (400, 422)
        assert client.post("/api/v1/plants", headers=h, json={"name": "x", "growing_environment": "moon"}).status_code in (400, 422)
        assert client.get("/api/v1/plants?page_size=1000", headers=h).status_code in (400, 422)

    def test_other_users_cannot_access_a_plant(self, client):
        owner = make_auth_header(client, email="owner2@example.com")
        intruder = make_auth_header(client, email="intruder@example.com")
        p = _create_plant(client, owner)
        pid = p["id"]
        assert client.get(f"/api/v1/plants/{pid}", headers=intruder).status_code == 404
        assert client.patch(f"/api/v1/plants/{pid}", headers=intruder, json={"name": "mine"}).status_code == 404
        assert client.delete(f"/api/v1/plants/{pid}", headers=intruder).status_code == 404
        assert client.get(f"/api/v1/plants/{pid}/timeline", headers=intruder).status_code == 404
        assert client.get("/api/v1/plants", headers=intruder).json()["total"] == 0
        # cannot attach a scan to someone else's plant
        resp = client.post("/api/v1/scans", headers=intruder, files={"image": _img()}, data={"plant_profile_id": pid})
        assert resp.status_code == 404
        assert client.get(f"/api/v1/diagnoses?plant_profile_id={pid}", headers=intruder).status_code == 404


class TestObservations:
    def test_scan_into_existing_and_new_plant_and_timeline(self, client):
        h = make_auth_header(client, email="timeline@example.com")
        p = _create_plant(client, h)
        r1 = client.post("/api/v1/scans", headers=h, files={"image": _img(1)},
                         data={"plant_profile_id": p["id"], "note": "Spots appeared after rain"})
        assert r1.status_code == 201, r1.text
        body = r1.json()
        assert body["plant_profile"]["id"] == p["id"]
        assert body["decision_status"] == "confident"
        assert body["measurement_basis"] is None and body["segmentation"]["status"] == "unavailable"
        assert "affected_area_not_measured" in body["limitations"]

        r2 = client.post("/api/v1/scans", headers=h, files={"image": _img(2)}, data={"new_plant_name": "Pepper bed"})
        assert r2.status_code == 201
        assert r2.json()["plant_profile"]["name"] == "Pepper bed"

        both = client.post("/api/v1/scans", headers=h, files={"image": _img(3)},
                           data={"plant_profile_id": p["id"], "new_plant_name": "x"})
        assert both.status_code == 400

        client.post("/api/v1/scans", headers=h, files={"image": _img(4)}, data={"plant_profile_id": p["id"]})
        tl = client.get(f"/api/v1/plants/{p['id']}/timeline", headers=h).json()
        assert tl["total"] == 2
        assert tl["plant"]["observation_count"] == 2
        assert tl["measurement_series"] == [] and tl["measurement_series_note"] == "no_segmentation_measurements"
        assert tl["entries"][0]["notes"][0]["body"] == "Spots appeared after rain"
        first_ts = tl["entries"][0]["observation"]["diagnosed_at"]
        assert first_ts <= tl["entries"][1]["observation"]["diagnosed_at"]

    def test_compare_is_cautious_and_owner_scoped(self, client):
        h = make_auth_header(client, email="cmp@example.com")
        p = _create_plant(client, h)
        a = client.post("/api/v1/scans", headers=h, files={"image": _img(5)}, data={"plant_profile_id": p["id"]}).json()
        b = client.post("/api/v1/scans", headers=h, files={"image": _img(6)}, data={"plant_profile_id": p["id"]}).json()
        resp = client.get(f"/api/v1/plants/{p['id']}/compare?a={a['diagnosis_id']}&b={b['diagnosis_id']}", headers=h)
        assert resp.status_code == 200
        c = resp.json()["comparison"]
        assert c["same_plant"] is True
        assert c["summary"] == "change_cannot_be_established"
        assert c["measurement"]["reason"] == "no_segmentation_measurement"

        other = make_auth_header(client, email="cmp-intruder@example.com")
        assert client.get(f"/api/v1/plants/{p['id']}/compare?a={a['diagnosis_id']}&b={b['diagnosis_id']}",
                          headers=other).status_code == 404
        assert client.get(f"/api/v1/diagnoses/compare?a={a['diagnosis_id']}&b={b['diagnosis_id']}",
                          headers=other).status_code == 403

    def test_notes_are_append_only_and_owner_only(self, client):
        h = make_auth_header(client, email="notes@example.com")
        d = client.post("/api/v1/scans", headers=h, files={"image": _img(7)}).json()
        did = d["diagnosis_id"]
        r = client.post(f"/api/v1/diagnoses/{did}/notes", headers=h,
                        json={"note_type": "treatment_applied", "body": "Removed lower leaves"})
        assert r.status_code == 201
        assert client.post(f"/api/v1/diagnoses/{did}/notes", headers=h,
                           json={"note_type": "expert_feedback", "body": "x"}).status_code == 403
        assert client.post(f"/api/v1/diagnoses/{did}/notes", headers=h,
                           json={"note_type": "follow_up", "body": "x"}).status_code in (400, 422)
        notes = client.get(f"/api/v1/diagnoses/{did}/notes", headers=h).json()
        assert [n["note_type"] for n in notes] == ["treatment_applied"]

        intruder = make_auth_header(client, email="notes-intruder@example.com")
        assert client.get(f"/api/v1/diagnoses/{did}/notes", headers=intruder).status_code == 403
        assert client.post(f"/api/v1/diagnoses/{did}/notes", headers=intruder,
                           json={"note_type": "user_note", "body": "x"}).status_code == 403

    def test_follow_up_answers_are_validated_and_do_not_change_probabilities(self, client):
        h = make_auth_header(client, email="followup@example.com")
        d = client.post("/api/v1/scans", headers=h, files={"image": _img(8)}).json()
        did = d["diagnosis_id"]
        before = [c["probability_pct"] for c in d["differential"]["model_candidates"]]
        assert d["differential"]["follow_up_questions"]

        bad = client.post(f"/api/v1/diagnoses/{did}/follow-up", headers=h, json={"answers": {"nonsense": "x"}})
        assert bad.status_code == 400
        resp = client.post(f"/api/v1/diagnoses/{did}/follow-up", headers=h,
                           json={"answers": {"pests_seen": "yes", "recent_weather": "wet_or_humid",
                                             "affected_parts": ["leaves", "bogus"]}})
        assert resp.status_code == 200, resp.text
        diff = resp.json()
        assert diff["answers"] == {"pests_seen": "yes", "recent_weather": "wet_or_humid", "affected_parts": ["leaves"]}
        codes = {h_["code"] for h_ in diff["hints"]}
        assert "pests_seen_check_pest_damage" in codes
        after = [c["probability_pct"] for c in diff["model_candidates"]]
        assert after == before
        notes = client.get(f"/api/v1/diagnoses/{did}/notes", headers=h).json()
        assert notes[-1]["note_type"] == "follow_up"

    def test_assign_plant_records_audit_note_and_checks_ownership(self, client):
        h = make_auth_header(client, email="assign@example.com")
        p = _create_plant(client, h)
        d = client.post("/api/v1/scans", headers=h, files={"image": _img(9)}).json()
        did = d["diagnosis_id"]
        r = client.put(f"/api/v1/diagnoses/{did}/plant", headers=h, json={"plant_profile_id": p["id"]})
        assert r.status_code == 200 and r.json()["plant_profile"]["id"] == p["id"]
        notes = client.get(f"/api/v1/diagnoses/{did}/notes", headers=h).json()
        assert notes[-1]["note_type"] == "plant_link_change"

        other = make_auth_header(client, email="assign-other@example.com")
        foreign = _create_plant(client, other)
        assert client.put(f"/api/v1/diagnoses/{did}/plant", headers=h,
                          json={"plant_profile_id": foreign["id"]}).status_code == 404
        assert client.put(f"/api/v1/diagnoses/{did}/plant", headers=other,
                          json={"plant_profile_id": foreign["id"]}).status_code == 403
