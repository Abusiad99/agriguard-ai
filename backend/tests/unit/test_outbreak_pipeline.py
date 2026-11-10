"""Outbreak pipeline: grid, features (missing data never becomes 0), labels, sourced
suitability rule, validator, and train/evaluate/predict on SYNTHETIC data."""
from __future__ import annotations

import csv
from datetime import date, timedelta

import pytest

from ai.outbreak import grid, suitability
from ai.outbreak.features import (FEATURE_NAMES, DailyWeather, Observation, build_features, completeness,
                                  label_window)
from ai.outbreak.validate import validate_dataset
from tests.synthetic_fixtures import make_outbreak_dataset

AS_OF = date(2026, 6, 15)


class TestGrid:
    def test_cell_contains_point_and_has_stable_key(self):
        cell = grid.cell_for(10.13, 20.37, 0.25)
        assert cell.south <= 10.13 < cell.north and cell.west <= 20.37 < cell.east
        assert grid.cell_from_key(cell.key) == cell
        assert len(grid.neighbors(cell)) == 8

    @pytest.mark.parametrize("lat, lon", [(91, 0), (0, 181), (float("nan"), 0)])
    def test_invalid_coordinates_rejected(self, lat, lon):
        with pytest.raises(ValueError):
            grid.cell_for(lat, lon)

    def test_too_fine_resolution_rejected(self):
        with pytest.raises(ValueError):
            grid.cell_for(10, 20, 0.01)


class TestFeatures:
    def test_missing_weather_stays_missing(self):
        features = build_features(AS_OF, 7, [Observation(AS_OF - timedelta(3), True)], [], weather={})
        assert set(features) == set(FEATURE_NAMES)
        for name in ("temp_mean_7d", "rh_mean_7d", "precip_sum_7d", "fc_rh_mean"):
            assert features[name] is None
        assert features["area_positives_7d"] == 1.0
        assert completeness(features) < 0.2

    def test_partial_weather_needs_coverage(self):
        weather = {AS_OF - timedelta(i): DailyWeather(AS_OF - timedelta(i), 20.0, 15.0, 25.0, 80.0, 5.0, 1.0)
                   for i in range(3)}  # 3 of 7 days
        assert build_features(AS_OF, 7, [], [], weather)["temp_mean_7d"] is None
        weather.update({AS_OF - timedelta(i): DailyWeather(AS_OF - timedelta(i), 22.0, 15.0, 25.0, 80.0, 5.0, 1.0)
                        for i in range(3, 7)})
        features = build_features(AS_OF, 7, [], [], weather)
        assert features["temp_mean_7d"] == pytest.approx((3 * 20 + 4 * 22) / 7, abs=1e-3)
        assert features["precip_sum_7d"] == pytest.approx(7.0)

    def test_label_is_unknown_when_nobody_inspected(self):
        obs = [Observation(AS_OF - timedelta(10), True)]
        assert label_window(obs, AS_OF, 7) is None
        assert label_window(obs + [Observation(AS_OF + timedelta(2), False)], AS_OF, 7) == 0
        assert label_window(obs + [Observation(AS_OF + timedelta(2), True)], AS_OF, 7) == 1


class TestSuitability:
    profile = suitability.SuitabilityProfile(
        id="t", crop="potato", disease="late_blight", rule="hutton_criteria",
        parameters={"min_temperature_c": 10, "min_rh90_hours": 6, "consecutive_days": 2}, source="test", description="")

    def _weather(self, tmins, hours):
        return {AS_OF + timedelta(i): DailyWeather(AS_OF + timedelta(i), None, t, None, None, h, None)
                for i, (t, h) in enumerate(zip(tmins, hours))}

    def test_two_consecutive_qualifying_days(self):
        result = suitability.evaluate(self.profile, self._weather([12, 11, 8], [7, 6, 9]), AS_OF, AS_OF + timedelta(2))
        assert result["status"] == "met"
        assert result["periods"] == [{"start": AS_OF.isoformat(), "end": (AS_OF + timedelta(1)).isoformat()}]
        assert result["kind"] == "rule_based_suitability"

    def test_not_met_and_missing_weather(self):
        assert suitability.evaluate(self.profile, self._weather([12, 9, 12], [7, 7, 7]), AS_OF, AS_OF + timedelta(2))["status"] == "not_met"
        assert suitability.evaluate(self.profile, {}, AS_OF, AS_OF + timedelta(2))["status"] == "insufficient_weather_data"

    def test_shipped_profiles_cite_sources(self):
        profiles = suitability.load_profiles()
        assert profiles and all(p.source for p in profiles)

    def test_profile_without_source_is_rejected(self, tmp_path):
        path = tmp_path / "p.json"
        path.write_text('{"profiles": [{"id": "x", "crop": "a", "disease": "b", "rule": "hutton_criteria", '
                        '"parameters": {}, "source": "", "description": ""}]}')
        with pytest.raises(ValueError):
            suitability.load_profiles(path)


class TestValidator:
    def test_synthetic_dataset_is_valid(self, tmp_path):
        root = make_outbreak_dataset(tmp_path / "ds", years=1, areas=((10.1, 20.1),))
        report = validate_dataset(root)
        assert report["summary"]["ready_for_preprocessing"], report["issues"][:5]
        assert report["statistics"]["observations"]["valid_rows"] > 40

    def test_errors_identify_line(self, tmp_path):
        raw = tmp_path / "ds" / "raw"
        raw.mkdir(parents=True)
        future = (date.today() + timedelta(days=5)).isoformat()
        with (raw / "observations.csv").open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["observed_on", "latitude", "longitude", "crop", "disease", "is_positive", "positive_count"])
            w.writerow(["2025-01-01", "95", "20", "tomato", "late_blight", "1", ""])      # out of range
            w.writerow(["not-a-date", "10", "20", "tomato", "late_blight", "1", ""])     # invalid value
            w.writerow([future, "10", "20", "tomato", "late_blight", "0", ""])           # future
            w.writerow(["2025-01-02", "10", "20", "tomato", "late_blight", "0", "2"])    # inconsistent
        report = validate_dataset(tmp_path / "ds")
        by_code = {i["code"]: i["line"] for i in report["issues"]}
        assert by_code["out_of_range"] == 2 and by_code["invalid_value"] == 3
        assert by_code["future_date"] == 4 and by_code["inconsistent_counts"] == 5
        assert "no_weather" in by_code
        assert report["summary"]["ready_for_preprocessing"] is False

    def test_missing_required_column(self, tmp_path):
        raw = tmp_path / "ds" / "raw"
        raw.mkdir(parents=True)
        (raw / "observations.csv").write_text("observed_on,latitude\n2025-01-01,10\n")
        assert "missing_columns" in {i["code"] for i in validate_dataset(tmp_path / "ds")["issues"]}


class TestTrainingAndPrediction:
    def test_trained_synthetic_model(self, trained_outbreak_artifacts, monkeypatch):
        from ai import registry
        from ai.config import CONFIG
        from ai.outbreak.model import OutbreakModel, risk_level

        monkeypatch.setattr(CONFIG.paths, "artifacts_dir", trained_outbreak_artifacts)
        card = registry.describe("outbreak")
        assert card.is_ready and card.architecture == "hist_gradient_boosting"
        assert card.details["score_kind"] in ("calibrated_probability", "risk_score")
        assert "test" in card.metrics and "roc_auc" in card.metrics["test"]

        model = OutbreakModel()
        assert model.supports("tomato", "late_blight") and not model.supports("tomato", "early_blight")
        humid = {AS_OF - timedelta(i): DailyWeather(AS_OF - timedelta(i), 20, 15, 25, 95, 20, 5) for i in range(-14, 14)}
        dry = {d: DailyWeather(d, 20, 15, 25, 40, 0, 0) for d in humid}
        high = model.predict(build_features(AS_OF, 7, [], [], humid), "tomato", "late_blight")
        low = model.predict(build_features(AS_OF, 7, [], [], dry), "tomato", "late_blight")
        assert high["score"] > low["score"]  # the synthetic signal was learned
        assert high["risk_level"] in ("low", "moderate", "high", "critical")
        factors = model.explain(build_features(AS_OF, 7, [], [], {}))
        assert factors and {"feature", "importance", "relation"} <= set(factors[0])
        assert risk_level(0.1, [0.25, 0.5, 0.75]) == "low" and risk_level(0.8, [0.25, 0.5, 0.75]) == "critical"

    def test_chronological_split_has_an_embargo(self, tmp_path):
        """No training label window may reach into the validation period, and no
        validation label window into the test period (label leakage)."""
        import pandas as pd

        from ai.outbreak.config import OutbreakConfig
        from ai.outbreak.preprocess import preprocess
        from ai.outbreak.train import chronological_split, load_table, split_summary
        from tests.synthetic_fixtures import make_outbreak_dataset

        root = make_outbreak_dataset(tmp_path / "ob")
        config = OutbreakConfig(min_rows=50, min_positives=10, min_negatives=10, min_span_days=200)
        preprocess(root, config)
        table, _ = load_table(root)
        train, val, test = chronological_split(table, config)
        end = lambda df: pd.to_datetime(df["as_of"]) + pd.to_timedelta(df["horizon_days"], unit="D")  # noqa: E731
        assert end(train).max() < pd.to_datetime(val["as_of"]).min()
        assert end(val).max() < pd.to_datetime(test["as_of"]).min()
        summary = split_summary(table, train, val, test)
        assert summary["purged_for_embargo"] > 0
        assert summary["train"] + summary["validation"] + summary["test"] + summary["purged_for_embargo"] == len(table)

    def test_trained_model_records_its_region_and_explains_without_reference(self, trained_outbreak_artifacts, monkeypatch):
        from ai.config import CONFIG
        from ai.outbreak.model import OutbreakModel

        monkeypatch.setattr(CONFIG.paths, "artifacts_dir", trained_outbreak_artifacts)
        model = OutbreakModel()
        extent = model.bundle["extent"]
        lat_lo, lon_lo = extent["lat_index"][0], extent["lon_index"][0]
        assert model.covers(lat_lo, lon_lo) is True and model.covers(lat_lo - 1, lon_lo) is True
        assert model.covers(lat_lo - 5, lon_lo) is False
        assert model.grid_resolution_deg == 0.25
        # A model trained without some feature (e.g. no weather file) has no reference range for it:
        # explaining a live value must not crash.
        name = next(iter(model.bundle["importance"]))
        model.bundle["reference"][name] = {"p25": None, "p50": None, "p75": None}
        model.bundle["importance"][name] = 1e9
        factors = model.explain({n: 1.0 for n in model.bundle["importance"]})
        assert factors[0]["feature"] == name and factors[0]["relation"] == "not_in_training_data"
        card = model.card["details"]
        assert card["forecast_features_training_source"].startswith("observed_weather")
        assert model.card["metrics"]["split_sizes"]["purged_for_embargo"] >= 0

    def test_refuses_to_train_on_too_little_data(self, tmp_path):
        from ai.outbreak.config import OutbreakConfig
        from ai.outbreak.preprocess import preprocess
        from ai.outbreak.train import InsufficientData, train

        root = make_outbreak_dataset(tmp_path / "ds", years=1, areas=((10.1, 20.1),))
        preprocess(root, OutbreakConfig())
        with pytest.raises(InsufficientData):
            train(root, OutbreakConfig())  # default minimums: 200 rows, 30 positives, 365 days


class TestScanObservationDate:
    """A located scan is counted on its UTC day, like every outbreak window (utc_today).
    PostgreSQL returns timestamps in its session time zone; in a zone ahead of UTC a scan
    made before UTC midnight was dated the next day and fell outside "until today"."""

    def _record(self, diagnosed_at):
        from types import SimpleNamespace
        from uuid import uuid4

        from app.application.services.outbreak_service import OutbreakService

        class Repo:  # stand-in: records the observation instead of writing it
            row = None

            def observation_for_diagnosis(self, _diagnosis_id):
                return None

            def get_or_create_area(self, _cell):
                return SimpleNamespace(id=uuid4())

            def add_observation(self, row):
                self.row = row
                return row

        repo = Repo()
        scan = SimpleNamespace(id=uuid4(), location_lat=10.31, location_lon=20.41, predicted_condition="early_blight",
                               unrecognized_plant=False, low_confidence_flag=False, diagnosed_at=diagnosed_at)
        OutbreakService(repo, model_client=None, weather=None).record_scan_observation(scan, "tomato")
        return repo.row.observed_on

    def test_scan_in_a_zone_ahead_of_utc_counts_on_its_utc_day(self):
        from datetime import datetime, timezone

        riyadh = timezone(timedelta(hours=3))
        # 01:00 on 11 Nov in UTC+3 is 22:00 on 10 Nov in UTC
        assert self._record(datetime(2026, 11, 11, 1, 0, tzinfo=riyadh)) == date(2026, 11, 10)

    def test_naive_timestamps_are_read_as_utc(self):
        from datetime import datetime

        assert self._record(datetime(2026, 11, 10, 23, 30)) == date(2026, 11, 10)
