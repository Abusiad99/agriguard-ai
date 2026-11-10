"""Agricultural reports: generation from real records, provenance on every value,
versioning, authorization, PDFs (English and Arabic), map export and share links.
All scans, knowledge-base rows and observations here are SYNTHETIC test fixtures."""
from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image

from tests.conftest import make_auth_header

LAT, LON = 10.3123, 20.4189


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
def kb(db_session):
    """SYNTHETIC knowledge-base entry for the fake classifier's prediction (tomato / early_blight)."""
    from app.infrastructure.db.models.knowledge_base_model import DiseaseModel, PlantModel, TreatmentModel

    plant = db_session.query(PlantModel).filter_by(canonical_name="tomato").one_or_none() or PlantModel(canonical_name="tomato")
    db_session.add(plant)
    db_session.flush()
    disease = DiseaseModel(plant_id=plant.id, name="early_blight", description="Test description (synthetic).",
                           symptoms_json=["dark concentric spots"], causes_json=["fungus (test)"],
                           transmission_method="spores (test)")
    db_session.add(disease)
    db_session.flush()
    db_session.add_all([
        TreatmentModel(disease_id=disease.id, category="organic", instructions="Remove affected leaves (test)."),
        TreatmentModel(disease_id=disease.id, category="chemical", instructions="Product X 2 ml per litre (test).",
                       authority_referral_only=True)])
    db_session.commit()
    return disease


def _facts(content):
    yield from content["key_facts"]
    for sec in content["sections"]:
        yield from sec["facts"]
        for row in sec.get("rows") or []:
            yield from row["cells"]


def _report(client, headers, **body):
    resp = client.post("/api/v1/agri-reports", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestDiagnosisReport:
    def test_every_value_has_a_source_and_predictions_stay_predictions(self, client, kb):
        owner = make_auth_header(client, email="rep1@example.com")
        dx = _scan(client, owner)
        report = _report(client, owner, type="diagnosis", subject_id=dx["diagnosis_id"], locale="en")
        c = report["content"]
        assert report["version"] == 1 and report["reference"].startswith("AGR-DX-") and report["data_hash"]
        for f in _facts(c):
            assert f["provenance"]["kind"], f
            if not f["available"]:
                assert f["reason_code"] and f["display"]
        facts = {f["key"]: f for f in _facts(c)}
        assert facts["condition"]["provenance"]["kind"] == "model"
        assert facts["severity"]["provenance"]["kind"] == "model_estimate"           # Grad-CAM, never a measurement
        assert facts["area_estimate"]["provenance"]["kind"] == "model_estimate"
        assert facts["area_measured"]["available"] is False                            # no segmentation model here
        assert facts["kb_match"]["provenance"]["kind"] == "knowledge_base"
        sections = {s["id"]: s for s in c["sections"]}
        alts = sections["alternatives"]["rows"]                                           # stored top-3
        assert [r["cells"][1]["value"] for r in alts] == [6.0, 2.5]
        assert not any(f.get("value") == "critical" for f in _facts(c))
        # the referral-only chemical treatment never shows its stored dose
        assert "2 ml" not in json.dumps(c)
        # v2: chapters in assessment order, every section placed in one
        assert [ch["id"] for ch in c["chapters"]] == ["summary", "condition", "evidence", "visual", "interpretation",
                                                      "actions", "monitoring", "limitations", "references"]
        assert all(s.get("chapter") in {ch["id"] for ch in c["chapters"]} for s in c["sections"])
        # reasoning: typed statements; confidence is never presented as accuracy
        kinds = [st["kind"] for st in sections["reasoning"]["statements"]]
        assert kinds[0] == "model" and "reference" in kinds and "estimate" in kinds and "measured" not in kinds
        assert facts["margin"]["value"] == 85.5 and facts["margin"]["provenance"]["kind"] == "rule"
        assert facts["test_precision"]["available"] is False                           # this test model has no test metrics
        ref_ids = {r["id"] for r in c["references"]}
        assert {"ref-calibration", "ref-field-gap", "ref-gradcam"} <= ref_ids
        assert [r["n"] for r in c["references"]] == list(range(1, len(c["references"]) + 1))
        assert all(r["url"].startswith("https://") and r["title"] and r["claims"] for r in c["references"])
        # visual panels explain themselves; the heatmap cites Grad-CAM and is never a mask
        heat = next(m for m in c["media"] if m["kind"] == "attention_heatmap")
        assert heat["explanation"] and heat["refs"] == ["ref-gradcam"] and heat["provenance"]["kind"] == "model_estimate"
        # missing information is listed with reasons
        missing = {m["key"]: m["reason_code"] for m in c["missing"]}
        assert missing["area_measured"] == "no_segmentation_model" and missing["untreated"] == "not_in_kb"
        recs = {r["rule"]: r for r in c["recommendations"]}
        assert {"R-KB-TREATMENT", "R-RESCAN", "R-PREVENT-SPREAD", "R-PREVENT-LONG"} <= set(recs)
        assert recs["R-KB-TREATMENT"]["basis"] == "knowledge_base" and recs["R-KB-TREATMENT"]["horizon"] == "short_term"
        assert recs["R-PREVENT-LONG"]["basis"] == "reference" and "ref-umn-prevention" in recs["R-PREVENT-LONG"]["refs"]
        assert recs["R-PREVENT-LONG"]["general_practice"] is True
        assert recs["R-RESCAN"]["refs"] == ["ref-umn-prevention"]                         # weekly scouting
        for r in c["recommendations"]:
            assert r["reason"] and r["timing"] and r["objective"] and r["horizon"] and r["basis"]
            assert set(r["refs"]) <= ref_ids
            if r["basis"] == "general_guidance":
                assert r["provenance"]["kind"] == "general_guidance"
        assert [r["horizon"] for r in c["recommendations"]] == sorted(
            (r["horizon"] for r in c["recommendations"]), key=["immediate", "short_term", "long_term"].index)
        plan = sections["monitoring_plan"]["items"]
        assert plan[0]["when"] and plan[0]["refs"] == ["ref-umn-prevention"]
        # no Gemini key in tests -> deterministic summary, every sentence cites facts
        assert c["narrative"]["source"] == "template" and c["narrative"]["executive_summary"]
        assert all(s["fact_ids"] for s in c["narrative"]["executive_summary"])
        assert "not a confirmed diagnosis" in c["narrative"]["executive_summary"][0]["text"]
        photo = next(m for m in c["media"] if m["kind"] == "photo")
        assert photo["url"].startswith("/api/v1/media/scans/") and "storage_key" not in photo
        assert client.get(photo["url"]).status_code == 200

    def test_versions_regenerate_and_archive(self, client, kb):
        owner = make_auth_header(client, email="rep2@example.com")
        dx = _scan(client, owner)
        first = _report(client, owner, type="diagnosis", subject_id=dx["diagnosis_id"], locale="en")
        second = client.post(f"/api/v1/agri-reports/{first['id']}/regenerate", headers=owner, json={"locale": "ar"}).json()
        assert second["version"] == 2 and second["supersedes_id"] == first["id"] and second["locale"] == "ar"
        assert second["data_hash"] == first["data_hash"]  # same source data -> same fingerprint
        versions = client.get(f"/api/v1/agri-reports/{second['id']}/versions", headers=owner).json()
        assert [v["version"] for v in versions] == [2, 1]
        listing = client.get("/api/v1/agri-reports?type=diagnosis&q=tomato", headers=owner).json()
        assert listing["total"] == 2
        assert client.get("/api/v1/agri-reports?q=nothing-matches", headers=owner).json()["total"] == 0
        # the original version is unchanged
        assert client.get(f"/api/v1/agri-reports/{first['id']}", headers=owner).json()["locale"] == "en"

    def test_simultaneous_requests_get_the_next_version_not_a_server_error(self, client, kb, monkeypatch):
        """Two requests for the same subject can both read "latest = v1" and both try v2;
        the unique (owner, type, subject, version) constraint rejects one. It now retries
        with the next number instead of failing with a 500."""
        from app.infrastructure.repositories.report_center_repository import SqlAlchemyReportCenterRepository

        owner = make_auth_header(client, email="rep-race@example.com")
        dx = _scan(client, owner)
        first = _report(client, owner, type="diagnosis", subject_id=dx["diagnosis_id"], locale="en")
        real_latest = SqlAlchemyReportCenterRepository.latest_version
        calls = {"n": 0}

        def stale_once(self, *args):  # the first read misses the version written by the "other" request
            calls["n"] += 1
            return None if calls["n"] == 1 else real_latest(self, *args)

        monkeypatch.setattr(SqlAlchemyReportCenterRepository, "latest_version", stale_once)
        second = _report(client, owner, type="diagnosis", subject_id=dx["diagnosis_id"], locale="en")
        assert calls["n"] == 2 and second["version"] == 2 and second["supersedes_id"] == first["id"]

    def test_arabic_report_and_pdfs(self, client, kb):
        owner = make_auth_header(client, email="rep3@example.com")
        dx = _scan(client, owner)
        ar = _report(client, owner, type="diagnosis", subject_id=dx["diagnosis_id"], locale="ar")
        assert ar["content"]["title"].startswith("تقرير تشخيص النبات")
        assert any("٪" in (f.get("display") or "") for f in _facts(ar["content"]))
        en = _report(client, owner, type="diagnosis", subject_id=dx["diagnosis_id"], locale="en")
        for rep in (ar, en):
            pdf = client.get(f"/api/v1/agri-reports/{rep['id']}/pdf", headers=owner)
            assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and len(pdf.content) > 5000
            assert pdf.headers["cache-control"].startswith("private")
            assert pdf.content.count(b"/Subtype /Image") >= 2  # the scan photo and the heatmap are embedded

    def test_other_users_get_nothing(self, client, kb):
        owner = make_auth_header(client, email="rep4@example.com")
        other = make_auth_header(client, email="rep5@example.com")
        dx = _scan(client, owner)
        rep = _report(client, owner, type="diagnosis", subject_id=dx["diagnosis_id"])
        assert client.get(f"/api/v1/agri-reports/{rep['id']}", headers=other).status_code == 404
        assert client.get(f"/api/v1/agri-reports/{rep['id']}/pdf", headers=other).status_code == 404
        assert client.post("/api/v1/agri-reports", headers=other,
                           json={"type": "diagnosis", "subject_id": dx["diagnosis_id"]}).status_code == 403
        assert client.get("/api/v1/agri-reports", headers=other).json()["total"] == 0
        assert client.get(f"/api/v1/agri-reports/{rep['id']}").status_code == 401


class TestShares:
    def test_share_lifecycle(self, client, kb, db_session):
        owner = make_auth_header(client, email="share1@example.com")
        dx = _scan(client, owner)
        rep = _report(client, owner, type="diagnosis", subject_id=dx["diagnosis_id"])
        created = client.post(f"/api/v1/agri-reports/{rep['id']}/shares", headers=owner, json={"expires_in_days": 3}).json()
        token = created["token"]
        shared = client.get(f"/api/v1/shared-reports/{token}")  # no login
        assert shared.status_code == 200
        body = shared.json()
        assert "sources" not in body and "subject_id" not in body and body["content"]["title"] == rep["content"]["title"]
        # no internal record ids anywhere in a shared copy
        shared_json = json.dumps(body)
        assert dx["diagnosis_id"] not in shared_json and '"record"' not in shared_json
        photo = next(m for m in body["content"]["media"] if m["kind"] == "photo")
        assert client.get(photo["url"]).status_code == 200
        assert client.get(f"/api/v1/shared-reports/{token}/pdf").content.startswith(b"%PDF")
        listed = client.get(f"/api/v1/agri-reports/{rep['id']}/shares", headers=owner).json()
        assert listed[0]["state"] == "active" and listed[0]["access_count"] == 2 and "token" not in listed[0]
        # tokens are stored only as hashes
        from app.infrastructure.db.models.report_center_model import ReportShareModel
        assert token not in {s.token_hash for s in db_session.query(ReportShareModel)}
        assert client.delete(f"/api/v1/agri-reports/{rep['id']}/shares/{created['id']}", headers=owner).json()["state"] == "revoked"
        assert client.get(f"/api/v1/shared-reports/{token}").status_code == 404

    def test_expired_and_invalid_links(self, client, kb, db_session):
        from app.infrastructure.db.models.report_center_model import ReportShareModel

        owner = make_auth_header(client, email="share2@example.com")
        other = make_auth_header(client, email="share3@example.com")
        dx = _scan(client, owner)
        rep = _report(client, owner, type="diagnosis", subject_id=dx["diagnosis_id"])
        created = client.post(f"/api/v1/agri-reports/{rep['id']}/shares", headers=owner, json={"expires_in_days": 1}).json()
        row = db_session.get(ReportShareModel, __import__("uuid").UUID(created["id"]))
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()
        assert client.get(f"/api/v1/shared-reports/{created['token']}").status_code == 404
        assert client.get("/api/v1/shared-reports/" + "x" * 43).status_code == 404
        assert client.post(f"/api/v1/agri-reports/{rep['id']}/shares", headers=owner,
                           json={"expires_in_days": 400}).status_code == 400
        assert client.post(f"/api/v1/agri-reports/{rep['id']}/shares", headers=other,
                           json={"expires_in_days": 3}).status_code == 404


class TestPlantAndAreaReports:
    def test_plant_progress_report_is_honest_without_measurements(self, client, kb):
        owner = make_auth_header(client, email="pp1@example.com")
        first = _scan(client, owner)
        plant = client.post("/api/v1/tracked-plants", headers=owner,
                            json={"name": "Row 3 (test)", "crop": "tomato", "initial_diagnosis_id": first["diagnosis_id"]}).json()
        _scan(client, owner, tracked_plant_id=plant["id"], treatment_stage="after_treatment")
        client.post(f"/api/v1/tracked-plants/{plant['id']}/treatments", headers=owner,
                    json={"name": "Removed leaves", "category": "cultural", "applied_on": datetime.now().date().isoformat()})
        rep = _report(client, owner, type="plant_progress", subject_id=plant["id"], locale="en")
        c = rep["content"]
        facts = {f["key"]: f for f in _facts(c)}
        assert c["status"]["code"] == "inconclusive" and facts["area_change"]["available"] is False
        # no comparable measurements -> no area chart; the severity chart is labelled an estimate
        assert not any(ch["id"] == "area_trend" for ch in c["charts"])
        assert all(ch["provenance"]["kind"] == "model_estimate" for ch in c["charts"])
        sections = {s["id"]: s for s in c["sections"]}
        table = sections["scan_table"]["rows"]
        assert len(table) == 2
        comparable = [next(x for x in row["cells"] if x["key"] == "comparable") for row in table]
        assert all(x["value"] is False for x in comparable)                             # and each row says why
        assert sections["measured_changes"]["facts"][0]["available"] is False
        # treatment shown next to measurements that do not exist -> explicit gaps, no inference
        tr_row = sections["treatments"]["rows"][0]["cells"]
        assert {x["key"]: x["available"] for x in tr_row}["before"] is False
        assert any(st["kind"] == "rule" for st in sections["status"]["statements"])
        assert any(r["rule"] == "R-PP-COMPARABLE" for r in c["recommendations"])
        assert all(r["horizon"] and r["basis"] for r in c["recommendations"])
        other = make_auth_header(client, email="pp2@example.com")
        assert client.post("/api/v1/agri-reports", headers=other,
                           json={"type": "plant_progress", "subject_id": plant["id"]}).status_code == 404

    def test_area_report_separates_observations_from_predictions(self, client, db_session):
        from tests.integration.test_outbreak_api import _seed_inspections

        _seed_inspections(db_session, 8)
        owner = make_auth_header(client, email="oa1@example.com")
        rep = _report(client, owner, type="outbreak_area", crop="tomato", disease="late_blight",
                      latitude=LAT, longitude=LON, locale="en")
        c = rep["content"]
        facts = {f["key"]: f for f in _facts(c)}
        assert facts["inspections"]["value"] == 8 and facts["inspections"]["provenance"]["kind"] == "observation"
        assert facts["risk_level"]["available"] is False  # no outbreak model -> no estimate, never a made-up level
        assert c["status"]["code"] == "no_current_estimate"
        assert str(LAT) not in json.dumps(rep) and str(LON) not in json.dumps(rep)
        png = client.get(f"/api/v1/agri-reports/{rep['id']}/map.png", headers=owner)
        assert png.status_code == 200 and png.content.startswith(b"\x89PNG")
        pdf = client.get(f"/api/v1/agri-reports/{rep['id']}/pdf", headers=owner)
        assert pdf.content.startswith(b"%PDF")
        # v2: the cell is never presented as a farm; coverage and the regional chapter title
        assert c["chapters"][1]["title"] == "Regional condition"
        assert any("not any single farm" in lim for lim in c["limitations"])
        # regenerating an area report keeps its area, crop, disease and period
        again = client.post(f"/api/v1/agri-reports/{rep['id']}/regenerate", headers=owner, json={"locale": "ar"})
        assert again.status_code == 201, again.text
        assert again.json()["version"] == 2 and again.json()["content"]["subject"]["area_id"] == c["subject"]["area_id"]
        assert client.post("/api/v1/agri-reports", headers=owner,
                           json={"type": "outbreak_area", "latitude": LAT, "longitude": LON}).status_code == 400
