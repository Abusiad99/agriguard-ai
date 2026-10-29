"""Calibration math and decision statuses (synthetic logits — tests of the math, not of a model)."""
from __future__ import annotations

import numpy as np
import pytest

from ai.inference.calibration import (
    CalibrationArtifact,
    calibration_metrics,
    evaluate_thresholds,
    expected_calibration_error,
    fit_temperature,
    isotonic_increasing,
    risk_coverage_curve,
    select_thresholds,
    softmax,
)
from ai.inference.decision import CONFIDENT, INCONCLUSIVE, UNCERTAIN, DecisionThresholds, decide, resolve_thresholds


def _synthetic(n=4000, k=10, true_t=2.5, seed=0):
    """Labels are SAMPLED from softmax(z / true_t), so temperature true_t is exactly calibrated."""
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 3.0, size=(n, k))
    p = softmax(z, true_t)
    labels = np.array([rng.choice(k, p=row) for row in p])
    return z, labels


def test_fit_temperature_recovers_known_temperature():
    z, y = _synthetic()
    t = fit_temperature(z, y)
    assert abs(t - 2.5) < 0.25
    before = expected_calibration_error(softmax(z, 1.0), y)["ece"]
    after = expected_calibration_error(softmax(z, t), y)["ece"]
    assert after < before and after < 0.04


def test_temperature_does_not_change_predictions():
    z, _ = _synthetic(n=500)
    assert (softmax(z, 1.0).argmax(1) == softmax(z, 3.7).argmax(1)).all()


def test_metrics_on_perfect_and_uniform_predictions():
    y = np.array([0, 1, 2, 0])
    perfect = np.eye(3)[y]
    m = calibration_metrics(perfect, y)
    assert m["accuracy"] == 1.0 and m["brier"] == 0.0 and m["ece"] == pytest.approx(0.0)
    uniform = np.full((4, 3), 1 / 3)
    assert calibration_metrics(uniform, y)["nll"] == pytest.approx(np.log(3))


def test_risk_coverage_is_monotone_for_informative_confidence():
    conf = np.array([0.9, 0.8, 0.7, 0.2, 0.1])
    correct = np.array([1, 1, 1, 0, 0], dtype=bool)
    rc = risk_coverage_curve(conf, correct)
    assert rc["selective_accuracy"][:3] == [1.0, 1.0, 1.0]
    assert rc["coverage"][-1] == 1.0


def test_threshold_selection_meets_target_on_selection_split_and_is_reported_on_another():
    z, y = _synthetic(n=6000, true_t=1.0, seed=1)
    p = softmax(z, 1.0)
    sel = select_thresholds(p, y, target_selective_accuracy=0.9, target_candidate_topk_accuracy=0.75, top_k=3)
    assert sel.target_met and sel.confident_accuracy >= 0.9
    assert 0 <= sel.reject_threshold <= sel.confident_threshold <= 1
    assert sel.confident_coverage + sel.uncertain_coverage + sel.rejected_coverage == pytest.approx(1.0)
    z2, y2 = _synthetic(n=3000, true_t=1.0, seed=2)
    held_out = evaluate_thresholds(softmax(z2, 1.0), y2, sel.confident_threshold, sel.reject_threshold, 3)
    assert held_out["confident_accuracy"] > 0.85  # close to, not guaranteed equal to, the target


def test_isotonic_fit_is_monotone_and_pools_violators():
    fit = isotonic_increasing(np.array([0, 1, 0, 1, 1, 0, 1, 1], dtype=float))
    assert (np.diff(fit) >= 0).all()
    assert fit.tolist() == pytest.approx([0, 0.5, 0.5, 2 / 3, 2 / 3, 2 / 3, 1, 1])
    assert fit.mean() == pytest.approx(5 / 8)  # least-squares fit preserves the mean


def _probs_with_conf(conf, k=10):
    """Rows with top-1 probability exactly `conf`, ranked class 0 > 1 > 2 > the rest."""
    rows = []
    for c in conf:
        p1 = min(0.95 * c, 0.5 * (1 - c))
        p2 = min(0.9 * c, 0.3 * (1 - c))
        rest = (1 - c - p1 - p2) / (k - 3)
        rows.append([c, p1, p2] + [rest] * (k - 3))
    return np.array(rows)


def test_reject_threshold_follows_local_shortlist_reliability_not_band_average():
    # 100 confident images (always right), 300 mid-confidence images whose top-3
    # contains the truth, and a 100-image low-confidence tail whose top-3 is wrong
    # 70 % of the time. The whole band below the confident threshold still averages
    # 0.825 >= 0.75, which made the old band-average rule mark nothing inconclusive.
    rng = np.random.default_rng(0)
    conf = np.concatenate([rng.uniform(0.92, 0.99, 100), rng.uniform(0.45, 0.85, 300), rng.uniform(0.12, 0.3, 100)])
    p = _probs_with_conf(conf)
    y = np.zeros(len(conf), dtype=np.int64)
    y[100:400] = 1                                   # in the top-3 but not top-1
    tail = np.arange(400, 500)
    y[tail] = np.where(rng.random(100) < 0.7, 7, 2)  # 70 % outside the top-3
    sel = select_thresholds(p, y, target_selective_accuracy=0.9, target_candidate_topk_accuracy=0.75, top_k=3)
    assert sel.reject_method == "isotonic_local_topk"
    assert 0.3 < sel.reject_threshold <= 0.46  # the lowest mid-group confidence, above the whole tail
    assert sel.rejected_coverage == pytest.approx(0.2)
    assert sel.uncertain_topk_accuracy == pytest.approx(1.0)


def test_unreachable_target_is_flagged():
    rng = np.random.default_rng(3)
    p = softmax(rng.normal(size=(500, 20)), 1.0)
    y = rng.integers(0, 20, 500)  # labels unrelated to predictions
    sel = select_thresholds(p, y, target_selective_accuracy=0.99)
    assert not sel.target_met and sel.notes


def test_calibration_artifact_round_trip(tmp_path):
    z, y = _synthetic(n=800)
    p = softmax(z, 2.0)
    art = CalibrationArtifact(temperature=2.0, thresholds=select_thresholds(p, y), plant_mass_threshold=0.6,
                              validation_metrics_before={}, validation_metrics_after={})
    art.save(tmp_path)
    loaded = CalibrationArtifact.load(tmp_path)
    assert loaded.temperature == 2.0 and loaded.thresholds.confident_threshold == art.thresholds.confident_threshold
    assert CalibrationArtifact.load(tmp_path / "missing") is None


def test_decision_statuses():
    th = DecisionThresholds(confident=0.8, reject=0.3, plant_mass=0.6, source="validation", temperature=1.0, calibrated=True)
    assert decide(np.array([0.9, 0.05, 0.05]), 0.95, th).status == CONFIDENT
    assert decide(np.array([0.5, 0.3, 0.2]), 0.9, th).status == UNCERTAIN
    d = decide(np.array([0.2, 0.2, 0.2, 0.2, 0.2]), 0.4, th)
    assert d.status == INCONCLUSIVE and not d.plant_identified and d.normalized_entropy == pytest.approx(1.0)


def test_threshold_resolution_precedence(monkeypatch):
    from ai.config import CONFIG

    t = resolve_thresholds(None)
    assert t.source == "unvalidated_default" and not t.calibrated and t.temperature == 1.0
    monkeypatch.setattr(CONFIG.inference, "confident_threshold_override", 0.95)
    t2 = resolve_thresholds(None)
    assert t2.source == "env_override" and t2.confident == 0.95
