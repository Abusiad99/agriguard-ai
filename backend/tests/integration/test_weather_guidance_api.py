"""Weather guidance through the real API, scan PDF and v2 report. Weather readings, scans,
stored advice texts and AI analyses here are SYNTHETIC fixtures; the weather service is
replaced by a stub (no network)."""
from __future__ import annotations

import io
import json
import re
import uuid
from datetime import datetime, timezone

import pytest
from PIL import Image
from pypdf import PdfReader

from app.infrastructure.external.weather_client import WeatherConditions
from tests.conftest import make_auth_header

OLD_PHRASES = re.compile(r"favou?rable for spraying|fungal spread|Delay irrigation|nitrogen-heavy|regular fertilizing|"
                         r"next few hours", re.IGNORECASE)
WHEN = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)


def _image():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (70, 120, 50)).save(buf, format="JPEG")
    buf.seek(0)
    return ("leaf.jpg", buf, "image/jpeg")


@pytest.fixture()
def weather(monkeypatch):
    """Stub the module-level weather service: returns the SYNTHETIC reading set by the test."""
    from app.interface.api.v1 import dependencies

    state = {"conditions": None}
    monkeypatch.setattr(dependencies._weather_service, "get_conditions", lambda lat, lon: state["conditions"])

    def set_reading(**values):
        base = {"temperature_c": 22.0, "humidity_pct": 55.0, "wind_speed_kmh": 9.0, "rain_probability_pct": 10.0,
                "uv_index": 3.0, "retrieved_at": WHEN}
        base.update(values)
        state["conditions"] = WeatherConditions(**base)
    return set_reading


def _scan(client, headers, located=True):
    data = {"latitude": "10.31", "longitude": "20.41"} if located else {}
    resp = client.post("/api/v1/scans", headers=headers, files={"image": _image()}, data=data)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestDiagnosisApi:
    def test_new_scan_gets_sourced_guidance_in_both_languages(self, client, weather):
        weather(wind_speed_kmh=20.0)
        owner = make_auth_header(client, email="wx1@example.com")
        dx = _scan(client, owner)
        g = dx["weather_guidance"]
        # the same instant on every database, always sent in UTC
        assert g["verdict"] == "wait" and datetime.fromisoformat(g["observed_at"]) == WHEN
        assert g["observed_at"].endswith("+00:00")
        wind = next(i for i in g["items"] if i["code"] == "wind")
        assert wind["status"] == "caution" and wind["basis"] == "reference" and wind["refs"] == ["ref-spray-wind"]
        assert "20.0 km/h" in wind["text"]["en"] and "٢٠٫٠" in wind["text"]["ar"]
        assert g["limits"]["wind_max_kmh"] == pytest.approx(12.874752)
        assert g["measurements"]["wind_speed_kmh"] == {"state": "ok", "value": 20.0, "status": "high"}
        # legacy fields: the same sourced summary, no irrigation or fertilizer advice
        rec = dx["recommendation"]
        assert rec["spraying_advice"] == g["summary"]["en"]
        assert rec["irrigation_advice"] is None and rec["fertilizer_advice"] is None
        assert not OLD_PHRASES.search(json.dumps(dx))
        again = client.get(f"/api/v1/diagnoses/{dx['diagnosis_id']}", headers=owner).json()
        assert again["weather_guidance"] == g

    @pytest.mark.parametrize("reading, verdict", [
        ({}, "within_limits"),
        ({"rain_probability_pct": 60.0}, "wait"),           # exactly 60 % counts as likely
        ({"wind_speed_kmh": None}, "incomplete"),
        ({"wind_speed_kmh": None, "rain_probability_pct": None, "temperature_c": None, "humidity_pct": None}, "incomplete"),
    ])
    def test_verdicts_through_the_api(self, client, weather, reading, verdict):
        weather(**reading)
        owner = make_auth_header(client, email=f"wx-{verdict}-{len(reading)}@example.com")
        assert _scan(client, owner)["weather_guidance"]["verdict"] == verdict

    def test_scan_without_location_is_not_assessed(self, client, weather):
        owner = make_auth_header(client, email="wx2@example.com")
        dx = _scan(client, owner, located=False)
        assert dx["weather_guidance"]["verdict"] == "not_assessed" and dx["weather_guidance"]["items"] == []
        assert "could not be assessed" in dx["recommendation"]["spraying_advice"]

    def test_old_scan_uses_its_stored_measurements_not_its_stored_text(self, client, db_session):
        from app.infrastructure.db.models.diagnosis_model import RecommendationModel, WeatherSnapshotModel

        owner = make_auth_header(client, email="wx3@example.com")
        dx = _scan(client, owner, located=False)
        did = uuid.UUID(dx["diagnosis_id"])
        # what an older scan looks like: stored unsourced advice and a stored weather snapshot
        rec = db_session.query(RecommendationModel).filter_by(diagnosis_id=did).one()
        rec.spraying_advice = "Weather conditions are currently favorable for spraying."
        rec.irrigation_advice = "Delay irrigation; expected rainfall may be sufficient."
        rec.fertilizer_advice = "Hold off on nitrogen-heavy fertilizer until the plant's health stabilizes."
        db_session.add(WeatherSnapshotModel(diagnosis_id=did, temperature_c=30, humidity_pct=88, wind_speed_kmh=25,
                                            rain_probability_pct=5, uv_index=4, retrieved_at=WHEN))
        db_session.commit()
        body = client.get(f"/api/v1/diagnoses/{did}", headers=owner).json()
        assert body["weather_guidance"]["verdict"] == "wait"          # 25 km/h > 8 mph, from the stored reading
        assert body["recommendation"]["irrigation_advice"] is None and body["recommendation"]["fertilizer_advice"] is None
        assert not OLD_PHRASES.search(json.dumps(body))

    def test_healthy_prediction_gets_no_spraying_check(self, client, db_session, weather):
        from app.infrastructure.db.models.diagnosis_model import DiagnosisModel

        weather()
        owner = make_auth_header(client, email="wx4@example.com")
        dx = _scan(client, owner)
        row = db_session.get(DiagnosisModel, uuid.UUID(dx["diagnosis_id"]))
        row.predicted_condition, row.disease_id, row.severity_level = "healthy", None, None
        db_session.commit()
        body = client.get(f"/api/v1/diagnoses/{dx['diagnosis_id']}", headers=owner).json()
        assert body["weather_guidance"]["verdict"] == "not_applicable" and body["weather_guidance"]["items"] == []
        assert body["recommendation"] is None

    def test_stored_ai_analysis_is_filtered_and_flagged(self, client, db_session):
        from app.infrastructure.db.models.diagnosis_model import AiAnalysisModel

        owner = make_auth_header(client, email="wx5@example.com")
        dx = _scan(client, owner, located=False)
        did = uuid.UUID(dx["diagnosis_id"])
        db_session.query(AiAnalysisModel).filter_by(diagnosis_id=did).delete()
        db_session.add(AiAnalysisModel(
            diagnosis_id=did, status="ok", cv_consistency="consistent", urgency="medium", model_name="synthetic-test",
            diagnosis_explanation="The lesions are dark with concentric rings, consistent with early blight. "
                                  "Weather conditions are favourable for spraying today.",
            observed_symptoms_json=["concentric rings"], confidence_assessment="Confidence is high.",
            severity_explanation="Severity is an estimate from the heatmap.",
            treatment_guidance_json=["Remove infected leaves.", "Spray copper when no rain is forecast."],
            prevention_guidance_json=["Rotate crops next season.", "Avoid irrigating in humid weather."],
            environmental_risk="High humidity favours fungal spread."))
        db_session.commit()
        ai = client.get(f"/api/v1/diagnoses/{did}", headers=owner).json()["ai_analysis"]
        assert ai["weather_advice_removed"] is True
        a = ai["analysis"]
        assert a["diagnosis_explanation"] == "The lesions are dark with concentric rings, consistent with early blight."
        assert a["treatment_guidance"] == ["Remove infected leaves."]
        assert a["prevention_guidance"] == ["Rotate crops next season."]
        assert a["environmental_risk"] == "" and a["observed_symptoms"] == ["concentric rings"]
        # the stored text is kept unchanged for audit
        stored = db_session.query(AiAnalysisModel).filter_by(diagnosis_id=did).one()
        assert "favourable for spraying" in stored.diagnosis_explanation

    def test_clean_ai_analysis_is_not_flagged(self, client, db_session):
        from app.infrastructure.db.models.diagnosis_model import AiAnalysisModel

        owner = make_auth_header(client, email="wx6@example.com")
        dx = _scan(client, owner, located=False)
        did = uuid.UUID(dx["diagnosis_id"])
        db_session.query(AiAnalysisModel).filter_by(diagnosis_id=did).delete()
        db_session.add(AiAnalysisModel(diagnosis_id=did, status="ok", cv_consistency="consistent", urgency="low",
                                       diagnosis_explanation="Symptoms match.", treatment_guidance_json=["Remove infected leaves."],
                                       environmental_risk="Measured weather: temperature 22 °C."))
        db_session.commit()
        ai = client.get(f"/api/v1/diagnoses/{did}", headers=owner).json()["ai_analysis"]
        assert ai["weather_advice_removed"] is False and ai["analysis"]["environmental_risk"] == "Measured weather: temperature 22 °C."


class TestDocuments:
    def test_scan_pdf_shows_missing_and_invalid_readings_honestly(self, client, weather):
        weather(humidity_pct=None, temperature_c=None, wind_speed_kmh=-4.0)
        owner = make_auth_header(client, email="wx7@example.com")
        dx = _scan(client, owner)
        pdf = client.get(dx["report_url"], headers=owner)
        assert pdf.status_code == 200
        text = " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf.content)).pages)
        flat = re.sub(r"\s+", " ", text)
        assert "None" not in flat and "-4.0" not in flat                      # the invalid reading is never printed
        assert "Not recorded by the weather service" in flat and "Not a valid measurement" in flat
        assert "Spraying Conditions at Scan Time" in flat and "could not be fully assessed" in flat
        assert "Evaluate the Weather" in flat and "Rainfastness of Pesticides" in flat
        assert not OLD_PHRASES.search(flat)

    def test_v2_report_and_diagnosis_api_agree(self, client, weather):
        weather(rain_probability_pct=75.0)
        owner = make_auth_header(client, email="wx8@example.com")
        dx = _scan(client, owner)
        for locale in ("en", "ar"):
            rep = client.post("/api/v1/agri-reports", headers=owner,
                              json={"type": "diagnosis", "subject_id": dx["diagnosis_id"], "locale": locale})
            assert rep.status_code == 201, rep.text
            env = next(s for s in rep.json()["content"]["sections"] if s["id"] == "environment")
            g = dx["weather_guidance"]
            assert env["weather_verdict"] == g["verdict"] == "wait"
            assert [s["text"] for s in env["statements"]] == [g["summary"][locale]] + [i["text"][locale] for i in g["items"]]
            pdf = client.get(f"/api/v1/agri-reports/{rep.json()['id']}/pdf", headers=owner)
            assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
            if locale == "en":
                pdf_text = re.sub(r"\s+", " ", " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf.content)).pages))
                assert "None" not in pdf_text and "generally best avoided when rain is likely" in pdf_text
