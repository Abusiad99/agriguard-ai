"""Model registry readiness, image quality checks, and daily weather aggregation."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image, ImageDraw

from ai import registry
from ai.config import CONFIG
from ai.image_quality import assess
from ai.registry import Readiness


class TestRegistry:
    def test_no_dataset_no_model(self):
        for card in registry.describe_all():
            assert card.readiness == Readiness.DATASET_UNAVAILABLE and not card.is_ready

    def test_dataset_prepared_but_not_trained(self):
        marker = CONFIG.paths.datasets_dir / "segmentation" / "manifests" / "dataset_manifest.json"
        marker.parent.mkdir(parents=True)
        marker.write_text("{}")
        assert registry.describe("segmentation").readiness == Readiness.NOT_TRAINED

    def test_run_without_model_card_needs_training(self):
        run = CONFIG.paths.artifacts_dir / "segmentation" / "runs" / "r1"
        run.mkdir(parents=True)
        registry.mark_latest("segmentation", run)
        assert registry.describe("segmentation").readiness == Readiness.TRAINING_REQUIRED

    def test_ready_card_never_exposes_paths(self):
        run = CONFIG.paths.artifacts_dir / "outbreak" / "runs" / "r1"
        run.mkdir(parents=True)
        (run / "model_card.json").write_text(json.dumps({"name": "outbreak-risk", "version": "r1", "classes": ["a/b"]}))
        registry.mark_latest("outbreak", run)
        card = registry.describe("outbreak")
        assert card.is_ready and card.version == "r1"
        assert "run_dir" not in card.public_dict() and str(run) not in json.dumps(card.public_dict())

    def test_stale_latest_marker_is_ignored(self):
        base = CONFIG.paths.artifacts_dir / "runs"
        base.mkdir(parents=True)
        (base / "latest.json").write_text(json.dumps({"run_dir": "does-not-exist"}))
        assert registry.latest_run_dir("classification") is None


def _textured(size=(400, 300), brightness=128):
    rng = np.random.default_rng(0)
    arr = np.clip(rng.normal(brightness, 40, size[::-1] + (3,)), 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


class TestImageQuality:
    def test_good_image_is_acceptable(self):
        q = assess(_textured())
        assert q.acceptable and q.width == 400 and q.height == 300

    def test_each_problem_is_flagged(self):
        assert "too_small" in assess(_textured((100, 80))).issues
        assert "too_dark" in assess(_textured(brightness=10)).issues
        assert "overexposed" in assess(_textured(brightness=245)).issues
        flat = Image.new("RGB", (400, 300), (120, 160, 90))
        ImageDraw.Draw(flat).ellipse([100, 80, 300, 220], fill=(100, 150, 80))
        assert "blurry" in assess(flat).issues
        assert assess(flat).to_dict()["acceptable"] is False


class TestWeather:
    def test_missing_hours_leave_daily_values_missing(self):
        from app.infrastructure.external.weather_client import aggregate_hourly

        times = [f"2026-06-01T{h:02d}:00" for h in range(24)] + [f"2026-06-02T{h:02d}:00" for h in range(24)]
        temps = [15.0] * 24 + [None] * 10 + [20.0] * 14
        rh = [95.0] * 6 + [70.0] * 18 + [80.0] * 24
        rain = [0.5] * 24 + [None] * 24
        day1, day2 = aggregate_hourly(times, temps, rh, rain, date(2026, 6, 2), "test")
        assert day1.kind == "observed" and day2.kind == "forecast"
        assert day1.temperature_mean_c == 15.0 and day1.rh_hours_ge_90 == 6.0 and day1.precipitation_mm == 12.0
        assert day2.temperature_mean_c is None and day2.precipitation_mm is None  # not enough hours: not 0
        assert day2.relative_humidity_mean_pct == 80.0

    def test_current_weather_does_not_default_missing_values_to_zero(self):
        from app.infrastructure.external.weather_client import OpenMeteoWeatherClient

        response = MagicMock()
        response.json.return_value = {"current": {"temperature_2m": 21.0, "relative_humidity_2m": 60, "wind_speed_10m": 3}}
        response.raise_for_status.return_value = None
        with patch("app.infrastructure.external.weather_client.httpx.get", return_value=response):
            conditions = OpenMeteoWeatherClient().fetch(1.0, 2.0)
        assert conditions.rain_probability_pct is None and conditions.uv_index is None
        assert isinstance(conditions.retrieved_at, datetime) and conditions.retrieved_at.tzinfo == timezone.utc


def test_feature_dataset_folders_are_not_classification_data():
    from PIL import Image as _Image

    from ai.data.dataset_scanner import DatasetScanner

    seg_images = CONFIG.paths.datasets_dir / "segmentation" / "raw" / "images"
    seg_images.mkdir(parents=True)
    _Image.new("RGB", (8, 8)).save(seg_images / "leaf.png")
    assert DatasetScanner().discover_dataset_roots() == []
    assert registry.describe("classification").readiness == Readiness.DATASET_UNAVAILABLE
    tomato = CONFIG.paths.datasets_dir / "mydata" / "tomato___healthy"
    tomato.mkdir(parents=True)
    _Image.new("RGB", (8, 8)).save(tomato / "a.png")
    assert [p.name for p in DatasetScanner().discover_dataset_roots()] == ["mydata"]
    assert registry.describe("classification").readiness == Readiness.NOT_TRAINED


def test_describe_uses_a_pinned_run_dir(tmp_path):
    """A run pinned outside artifacts/runs (AI_ARTIFACTS_RUN_DIR) is described as served,
    even when no dataset is present on this machine."""
    run = tmp_path / "pinned_run"
    run.mkdir()
    (run / "model_meta.json").write_text(json.dumps({"architecture": "efficientnet_b0"}))
    (run / "label_encoder.json").write_text(json.dumps({"classes": ["tomato___healthy"]}))
    assert registry.describe("classification").readiness == Readiness.DATASET_UNAVAILABLE
    card = registry.describe("classification", run)
    assert card.readiness == Readiness.READY and card.version == "pinned_run" and card.classes == ["tomato___healthy"]
    assert registry.describe("classification", tmp_path / "missing").readiness == Readiness.DATASET_UNAVAILABLE
