"""Outbreak risk API: readiness, privacy-preserving map aggregation, honest predictions
(no model -> unavailable; missing weather -> insufficient data), synthetic trained model."""
from __future__ import annotations

import io
import json
from datetime import date, datetime, timedelta, timezone

import pytest
from PIL import Image

from app.application.services.outbreak_service import utc_today
from tests.conftest import make_auth_header

LAT, LON = 10.3123, 20.4189  # one grid cell at 0.25 deg (digits unlike any cell center)


def _image():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (70, 120, 50)).save(buf, format="JPEG")
    buf.seek(0)
    return ("leaf.jpg", buf, "image/jpeg")


def _located_scan(client, headers, lat=LAT, lon=LON):
    resp = client.post("/api/v1/scans", headers=headers, files={"image": _image()},
                       data={"latitude": lat, "longitude": lon, "attach_location": "true"})
    assert resp.status_code == 201, resp.text


class _NoWeather:
    def daily(self, lat, lon, start, end):
        from app.infrastructure.external.weather_client import WeatherProviderError
        raise WeatherProviderError("offline in tests")


class _FlatWeather:
    def __init__(self, rh):
        self.rh = rh

    def daily(self, lat, lon, start, end):
        from app.infrastructure.external.weather_client import DailyWeatherRecord
        days = (end - start).days + 1
        return [DailyWeatherRecord(start + timedelta(i), "observed" if start + timedelta(i) < utc_today() else "forecast",
                                   "test", 20, 15, 25, self.rh, max(0, (self.rh - 75) * 1.2), 1.0) for i in range(days)]


def _seed_inspections(db_session, n, lat=LAT, lon=LON, crop="tomato", disease="late_blight", positive_every=3):
    """SYNTHETIC survey rows in one grid cell (what `outbreak.ps1 -Action import` would add)."""
    from ai.outbreak import grid
    from app.core.config import get_settings
    from app.infrastructure.db.models.ai_features_model import DiseaseObservationModel
    from app.infrastructure.repositories.ai_features_repository import SqlAlchemyOutbreakRepository

    repo = SqlAlchemyOutbreakRepository(db_session)
    area = repo.get_or_create_area(grid.cell_for(lat, lon, get_settings().outbreak_grid_resolution_deg))
    for i in range(n):
        positive = i % positive_every == 0
        repo.add_observation(DiseaseObservationModel(
            area_id=area.id, source="dataset", dataset_version="synthetic-test", crop=crop, disease=disease,
            is_positive=positive, inspected_count=1, positive_count=int(positive),
            observed_on=utc_today() - timedelta(days=7 * (i + 1))), commit=False)
    db_session.commit()


@pytest.fixture()
def weather(monkeypatch):
    from app.interface.api.v1 import dependencies

    def use(provider):
        monkeypatch.setattr(dependencies, "_daily_weather", provider)
    use(_NoWeather())
    return use


def test_requires_login(client):
    for url in ("/api/v1/outbreak/readiness", "/api/v1/outbreak/map", "/api/v1/outbreak/filters"):
        assert client.get(url).status_code == 401


def test_readiness_is_honest_without_model_or_data(client):
    headers = make_auth_header(client, email="o1@example.com")
    body = client.get("/api/v1/outbreak/readiness", headers=headers).json()
    assert body["can_predict"] is False
    assert body["model"]["readiness"] == "dataset_unavailable"
    assert {"model_not_ready", "no_observations"} <= set(body["limitations"])
    assert body["suitability_profiles"] and all(p["source"] for p in body["suitability_profiles"])


def test_map_hides_cells_below_contributor_threshold_and_never_returns_coordinates(client):
    users = [make_auth_header(client, email=f"farmer{i}@example.com") for i in range(3)]
    _located_scan(client, users[0])
    _located_scan(client, users[1])
    params = {"crop": "tomato", "disease": "early_blight"}
    layer = client.get("/api/v1/outbreak/map", headers=users[0], params=params).json()
    assert layer["cells"] == [] and layer["hidden_for_privacy"] == 1

    _located_scan(client, users[2])
    layer = client.get("/api/v1/outbreak/map", headers=users[0], params=params).json()
    assert len(layer["cells"]) == 1
    cell = layer["cells"][0]
    assert cell["app_inspections"] == 3 and cell["positives"] == 3 and cell["app_counts_suppressed"] is False
    assert cell["area"]["bounds"]["south"] <= LAT <= cell["area"]["bounds"]["north"]
    text = json.dumps(layer)
    assert str(LAT) not in text and str(LON) not in text  # only the grid cell, never the scan location

    detail = client.get(f"/api/v1/outbreak/areas/{cell['area']['id']}", headers=users[0], params=params).json()
    assert detail["summary"]["positives"] == 3 and detail["trend"][0]["inspections"] == 3

    # The panel can use the map's window: a window that ends before today's scans is empty.
    today = datetime.now(timezone.utc).date()  # observations are dated in UTC
    yesterday = (today - timedelta(days=1)).isoformat()
    windowed = client.get(f"/api/v1/outbreak/areas/{cell['area']['id']}", headers=users[0],
                          params={**params, "date_from": (today - timedelta(days=30)).isoformat(), "date_to": yesterday})
    assert windowed.status_code == 200 and windowed.json()["summary"] is None and windowed.json()["trend"] == []
    inverted = client.get(f"/api/v1/outbreak/areas/{cell['area']['id']}", headers=users[0],
                          params={"date_from": today.isoformat(), "date_to": yesterday})
    assert inverted.status_code == 400


def test_unlocated_scans_never_become_observations(client):
    headers = make_auth_header(client, email="nolocation@example.com")
    client.post("/api/v1/scans", headers=headers, files={"image": _image()}, data={"latitude": LAT, "longitude": LON})
    assert client.get("/api/v1/outbreak/readiness", headers=headers).json()["data"]["app_scan_observations"] == 0


def test_prediction_without_model_is_unavailable_and_not_stored(client, weather):
    headers = make_auth_header(client, email="o2@example.com")
    resp = client.post("/api/v1/outbreak/predictions", headers=headers,
                       json={"crop": "potato", "disease": "late_blight", "horizon_days": 7, "latitude": LAT, "longitude": LON})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "model_unavailable" and body["risk_level"] == "unavailable" and body["persisted"] is False
    assert "weather_unavailable" in body["limitations"]
    assert body["suitability"][0]["status"] == "insufficient_weather_data"  # never "not met" on missing data
    assert client.get("/api/v1/outbreak/predictions", headers=headers).json()["total"] == 0


def test_prediction_never_reveals_history_from_too_few_users(client, weather):
    """Privacy: a prediction's history features are counts of other users' located scans.
    Below OUTBREAK_MIN_CONTRIBUTORS distinct users the map hides them, so the prediction
    response must not return them either (here: no trained model, nothing stored)."""
    from ai.outbreak.features import HISTORY_FEATURES

    _located_scan(client, make_auth_header(client, email="solo-scanner@example.com"))
    asker = make_auth_header(client, email="asker@example.com")
    body = client.post("/api/v1/outbreak/predictions", headers=asker, json={
        "crop": "tomato", "disease": "early_blight", "horizon_days": 7, "latitude": LAT, "longitude": LON}).json()
    assert body["status"] == "model_unavailable"
    assert "history_withheld_for_privacy" in body["limitations"]
    assert all(body["features"][name] is None for name in HISTORY_FEATURES)
    assert body["features"]["doy_sin"] is not None  # non-history features are still returned


def test_map_shows_only_the_survey_date_while_app_counts_are_suppressed(client, db_session):
    _seed_inspections(db_session, 3, crop="tomato", disease="early_blight")  # SYNTHETIC survey rows, 7-21 days ago
    _located_scan(client, make_auth_header(client, email="one-user@example.com"))  # today, 1 contributor
    viewer = make_auth_header(client, email="viewer@example.com")
    layer = client.get("/api/v1/outbreak/map", headers=viewer, params={"crop": "tomato", "disease": "early_blight"}).json()
    cell = layer["cells"][0]
    assert cell["app_counts_suppressed"] is True and cell["app_inspections"] is None
    assert cell["latest_observation"] == (utc_today() - timedelta(days=7)).isoformat()


def test_prediction_validation(client):
    headers = make_auth_header(client, email="o3@example.com")
    for body in ({"crop": "tomato", "disease": "x", "horizon_days": 30, "latitude": 1, "longitude": 1},
                 {"crop": "tomato", "disease": "x"},
                 {"crop": "tomato", "disease": "x", "latitude": 95, "longitude": 1}):
        assert client.post("/api/v1/outbreak/predictions", headers=headers, json=body).status_code == 400
    assert client.get("/api/v1/outbreak/map?bbox=1,2,3", headers=headers).status_code == 400


class TestWithSyntheticModel:
    @pytest.fixture(autouse=True)
    def model(self, trained_outbreak_artifacts, monkeypatch):
        from ai.config import CONFIG
        monkeypatch.setattr(CONFIG.paths, "artifacts_dir", trained_outbreak_artifacts)

    def test_missing_weather_gives_insufficient_data(self, client, weather):
        headers = make_auth_header(client, email="o4@example.com")
        body = client.post("/api/v1/outbreak/predictions", headers=headers, json={
            "crop": "tomato", "disease": "late_blight", "horizon_days": 7, "latitude": LAT, "longitude": LON}).json()
        assert body["status"] == "insufficient_data" and body["risk_level"] == "insufficient_data"
        assert body["score"] is None and body["persisted"] is True
        assert {"weather_unavailable", "low_data_completeness"} <= set(body["limitations"])

    def test_no_risk_level_without_local_history(self, client, weather):
        """Zero counts in a never-inspected cell mean "nobody looked", not "no disease"."""
        weather(_FlatWeather(rh=95))
        headers = make_auth_header(client, email="o6@example.com")
        body = client.post("/api/v1/outbreak/predictions", headers=headers, json={
            "crop": "tomato", "disease": "late_blight", "horizon_days": 7, "latitude": LAT, "longitude": LON}).json()
        assert body["status"] == "insufficient_data" and body["risk_level"] == "insufficient_data"
        assert body["score"] is None and "no_local_history" in body["limitations"]

    def test_no_risk_level_outside_training_region(self, client, weather, db_session):
        weather(_FlatWeather(rh=95))
        _seed_inspections(db_session, 10, lat=-33.9, lon=18.4)  # history exists, but far from the training cells
        headers = make_auth_header(client, email="o7@example.com")
        body = client.post("/api/v1/outbreak/predictions", headers=headers, json={
            "crop": "tomato", "disease": "late_blight", "horizon_days": 7, "latitude": -33.9, "longitude": 18.4}).json()
        assert body["status"] == "insufficient_data" and "outside_training_region" in body["limitations"]
        assert body["score"] is None

    def test_stored_prediction_withholds_history_until_enough_users_contributed(self, client, weather, db_session):
        from ai.outbreak.features import HISTORY_FEATURES

        weather(_FlatWeather(rh=95))
        _seed_inspections(db_session, 12)
        _located_scan(client, make_auth_header(client, email="first-scanner@example.com"))  # 1 contributor < 3
        asker = make_auth_header(client, email="o9@example.com")
        body = client.post("/api/v1/outbreak/predictions", headers=asker, json={
            "crop": "tomato", "disease": "late_blight", "horizon_days": 7, "latitude": LAT, "longitude": LON}).json()
        assert body["status"] == "ok" and "history_withheld_for_privacy" in body["limitations"]
        assert all(body["features"][name] is None for name in HISTORY_FEATURES)
        assert not {f["feature"] for f in body["factors"]} & set(HISTORY_FEATURES)  # factors carry values too

        url = f"/api/v1/outbreak/predictions/{body['prediction_id']}"
        stored = client.get(url, headers=asker).json()
        assert "history_withheld_for_privacy" in stored["limitations"]
        assert all(stored["features"][name] is None for name in HISTORY_FEATURES)
        assert not {f["feature"] for f in stored["factors"]} & set(HISTORY_FEATURES)

        for i in range(2):  # now 3 distinct users: the same stored prediction is shown in full
            _located_scan(client, make_auth_header(client, email=f"next-scanner{i}@example.com"))
        stored = client.get(url, headers=asker).json()
        assert "history_withheld_for_privacy" not in stored["limitations"]
        assert stored["features"]["area_inspections_30d"] is not None

    def test_grid_resolution_mismatch_is_refused(self, client, weather, monkeypatch):
        from app.application.services import outbreak_service

        monkeypatch.setattr(outbreak_service.settings, "outbreak_grid_resolution_deg", 0.5)
        weather(_FlatWeather(rh=95))
        headers = make_auth_header(client, email="o8@example.com")
        body = client.post("/api/v1/outbreak/predictions", headers=headers, json={
            "crop": "tomato", "disease": "late_blight", "horizon_days": 7, "latitude": LAT, "longitude": LON}).json()
        assert body["status"] == "model_unavailable" and body["reason"] == "grid_resolution_mismatch"

    def test_risk_prediction_with_weather(self, client, weather, db_session):
        weather(_FlatWeather(rh=95))
        _seed_inspections(db_session, 12)
        headers = make_auth_header(client, email="o5@example.com")
        body = client.post("/api/v1/outbreak/predictions", headers=headers, json={
            "crop": "tomato", "disease": "late_blight", "horizon_days": 7, "latitude": LAT, "longitude": LON}).json()
        assert body["status"] == "ok" and body["risk_level"] in ("low", "moderate", "high", "critical")
        assert 0 <= body["score"] <= 1 and body["score_kind"] in ("calibrated_probability", "risk_score")
        assert body["model_version"] and body["data_completeness"] >= 0.5 and body["factors"]
        assert body["forecast_end"] == (utc_today() + timedelta(days=7)).isoformat()
        stored = client.get(f"/api/v1/outbreak/predictions/{body['prediction_id']}", headers=headers).json()
        assert stored["risk_level"] == body["risk_level"] and stored["features"]

        assert "history_withheld_for_privacy" not in body["limitations"]  # survey data only: nothing to hide

        # predictions for pairs the model was not trained on are refused, not guessed
        other = client.post("/api/v1/outbreak/predictions", headers=headers, json={
            "crop": "tomato", "disease": "early_blight", "horizon_days": 7, "latitude": LAT, "longitude": LON}).json()
        assert other["status"] == "model_unavailable" and other["reason"] == "not_trained_for_crop_disease"
