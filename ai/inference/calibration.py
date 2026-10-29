"""
Confidence calibration and validation-based threshold selection.

Why this exists: a classifier's softmax output is NOT a calibrated probability that
its prediction is correct. Modern CNNs are typically over-confident (Guo et al.,
"On Calibration of Modern Neural Networks", ICML 2017). This module:

  * fits a single temperature T on the VALIDATION split by minimizing negative
    log-likelihood (temperature scaling — it changes confidence values but never
    changes which class is predicted);
  * measures calibration (ECE, MCE, Brier score, NLL) and selective-classification
    behaviour (risk–coverage curve, AURC);
  * selects decision thresholds from validation data against explicit targets,
    instead of hard-coding "60%" as if it were scientifically established.

Everything here is plain numpy so it can be unit-tested without a trained model.
The resulting `calibration.json` is stored next to the model weights and loaded by
InferenceService; thresholds selected here are always reported together with the
split they were selected on and the targets used.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

CALIBRATION_FILENAME = "calibration.json"
CALIBRATION_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Basic probability utilities
# ---------------------------------------------------------------------------
def softmax(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    z = np.asarray(logits, dtype=np.float64) / float(temperature)
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def negative_log_likelihood(probs: np.ndarray, labels: np.ndarray) -> float:
    p = np.clip(probs[np.arange(len(labels)), labels], 1e-12, 1.0)
    return float(-np.mean(np.log(p)))


def brier_score(probs: np.ndarray, labels: np.ndarray) -> float:
    """Multi-class Brier score: mean squared error between the probability vector and
    the one-hot label (0 = perfect, 2 = worst)."""
    onehot = np.zeros_like(probs)
    onehot[np.arange(len(labels)), labels] = 1.0
    return float(np.mean(np.sum((probs - onehot) ** 2, axis=1)))


@dataclass
class ReliabilityBin:
    lower: float
    upper: float
    count: int
    mean_confidence: Optional[float]
    accuracy: Optional[float]


def reliability_bins(probs: np.ndarray, labels: np.ndarray, n_bins: int = 15) -> List[ReliabilityBin]:
    conf = probs.max(axis=1)
    correct = (probs.argmax(axis=1) == labels).astype(np.float64)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (conf > lo) & (conf <= hi) if i > 0 else (conf >= lo) & (conf <= hi)
        n = int(mask.sum())
        bins.append(ReliabilityBin(
            lower=float(lo), upper=float(hi), count=n,
            mean_confidence=float(conf[mask].mean()) if n else None,
            accuracy=float(correct[mask].mean()) if n else None,
        ))
    return bins


def expected_calibration_error(probs: np.ndarray, labels: np.ndarray, n_bins: int = 15) -> Dict[str, float]:
    """ECE (count-weighted mean |accuracy - confidence| over bins) and MCE (max gap)."""
    total = len(labels)
    ece, mce = 0.0, 0.0
    for b in reliability_bins(probs, labels, n_bins):
        if b.count == 0:
            continue
        gap = abs(b.accuracy - b.mean_confidence)
        ece += (b.count / total) * gap
        mce = max(mce, gap)
    return {"ece": float(ece), "mce": float(mce)}


def fit_temperature(logits: np.ndarray, labels: np.ndarray,
                    grid: Optional[np.ndarray] = None) -> float:
    """Fit a single softmax temperature by minimizing validation NLL.

    A dense log-spaced grid followed by a local refinement is used instead of a
    gradient optimizer: the problem is 1-D and convex in log(T) for practical
    purposes, and a grid search cannot diverge or silently return NaN.
    """
    logits = np.asarray(logits, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.int64)
    if len(labels) == 0:
        raise ValueError("Cannot fit a temperature on an empty validation set.")
    grid = grid if grid is not None else np.exp(np.linspace(np.log(0.05), np.log(20.0), 400))
    nlls = np.array([negative_log_likelihood(softmax(logits, t), labels) for t in grid])
    best = int(np.argmin(nlls))
    lo = grid[max(0, best - 1)]
    hi = grid[min(len(grid) - 1, best + 1)]
    fine = np.linspace(lo, hi, 101)
    fine_nlls = np.array([negative_log_likelihood(softmax(logits, t), labels) for t in fine])
    return float(fine[int(np.argmin(fine_nlls))])


# ---------------------------------------------------------------------------
# Selective classification (risk–coverage)
# ---------------------------------------------------------------------------
def risk_coverage_curve(confidence: np.ndarray, correct: np.ndarray) -> Dict[str, list]:
    """Coverage and selective accuracy when only predictions with confidence >= t
    are accepted, for every distinct t (descending). Also returns AURC (area under
    the risk–coverage curve; lower is better)."""
    order = np.argsort(-confidence, kind="stable")
    conf_sorted = confidence[order]
    corr_sorted = correct[order].astype(np.float64)
    n = len(conf_sorted)
    cum_correct = np.cumsum(corr_sorted)
    k = np.arange(1, n + 1)
    coverage = k / n
    sel_acc = cum_correct / k
    risk = 1.0 - sel_acc
    aurc = float(np.mean(risk)) if n else float("nan")
    return {
        "threshold": conf_sorted.tolist(),
        "coverage": coverage.tolist(),
        "selective_accuracy": sel_acc.tolist(),
        "aurc": aurc,
    }


def summarize_risk_coverage(confidence: np.ndarray, correct: np.ndarray,
                            coverages=(1.0, 0.9, 0.8, 0.7, 0.6, 0.5)) -> List[Dict[str, float]]:
    curve = risk_coverage_curve(confidence, correct)
    cov = np.array(curve["coverage"])
    acc = np.array(curve["selective_accuracy"])
    thr = np.array(curve["threshold"])
    rows = []
    for c in coverages:
        if len(cov) == 0:
            break
        idx = int(np.searchsorted(cov, c, side="left"))
        idx = min(idx, len(cov) - 1)
        rows.append({"coverage": float(cov[idx]), "selective_accuracy": float(acc[idx]),
                     "confidence_threshold": float(thr[idx])})
    return rows


def isotonic_increasing(values: np.ndarray) -> np.ndarray:
    """Least-squares non-decreasing fit (pool-adjacent-violators) of `values`, which
    must already be ordered by the variable the fit should increase with. For a 0/1
    hit indicator ordered by confidence, the result estimates the hit rate at each
    confidence without choosing bin edges."""
    values = np.asarray(values, dtype=np.float64)
    means: List[float] = []
    sizes: List[int] = []
    for v in values:
        means.append(float(v))
        sizes.append(1)
        while len(means) > 1 and means[-2] > means[-1]:
            m2, n2 = means.pop(), sizes.pop()
            m1, n1 = means.pop(), sizes.pop()
            means.append((m1 * n1 + m2 * n2) / (n1 + n2))
            sizes.append(n1 + n2)
    return np.repeat(np.array(means), np.array(sizes, dtype=np.int64)) if means else values


# ---------------------------------------------------------------------------
# Threshold selection
# ---------------------------------------------------------------------------
@dataclass
class ThresholdSelection:
    confident_threshold: float
    reject_threshold: float
    target_selective_accuracy: float
    target_candidate_topk_accuracy: float
    candidate_top_k: int
    # What the selected thresholds achieved on the SELECTION split.
    selection_split: str
    selection_n: int
    confident_coverage: float
    confident_accuracy: Optional[float]
    uncertain_coverage: float
    uncertain_topk_accuracy: Optional[float]
    rejected_coverage: float
    target_met: bool
    notes: List[str] = field(default_factory=list)
    # "isotonic_local_topk" (current) or "band_average" (calibration files written
    # before the local rule was introduced).
    reject_method: str = "band_average"


def select_thresholds(probs: np.ndarray, labels: np.ndarray, *,
                      target_selective_accuracy: float = 0.90,
                      target_candidate_topk_accuracy: float = 0.75,
                      top_k: int = 3,
                      selection_split: str = "val") -> ThresholdSelection:
    """Choose two thresholds on (calibrated) top-1 probability:

    confident_threshold: the LOWEST threshold t such that predictions with
        confidence >= t reach `target_selective_accuracy` on this split (maximizes
        coverage subject to the accuracy target). If the target cannot be met at
        any threshold, the threshold with the best achievable selective accuracy
        among those covering >= 5% of samples is used and `target_met=False`.

    reject_threshold: the LOWEST confidence r (<= confident_threshold) at which the
        LOCAL rate of "true class among the top-k candidates" reaches the top-k
        target. The local rate is a monotone (isotonic) fit of the top-k hit
        indicator against confidence, so it describes images AT a given confidence
        rather than the average of the whole band. (Averaging the band let the many
        good images just below the confident threshold hide a low-confidence tail
        whose shortlist was usually wrong.) Below r the shortlist is unreliable on
        validation data, so the system reports "inconclusive" and names nothing.

    Note: these thresholds are validated only for IN-DISTRIBUTION images (the
    classes the model was trained on). They do not establish that out-of-
    distribution inputs (unsupported diseases, non-plant images) will fall below
    the reject threshold.
    """
    probs = np.asarray(probs, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.int64)
    n = len(labels)
    if n == 0:
        raise ValueError("Cannot select thresholds on an empty split.")
    conf = probs.max(axis=1)
    correct = probs.argmax(axis=1) == labels
    topk_idx = np.argsort(-probs, axis=1)[:, :top_k]
    in_topk = (topk_idx == labels[:, None]).any(axis=1)
    notes: List[str] = []

    order = np.argsort(-conf, kind="stable")
    conf_sorted = conf[order]
    corr_sorted = correct[order].astype(np.float64)
    cum_acc = np.cumsum(corr_sorted) / np.arange(1, n + 1)

    # --- confident threshold ---
    meets = np.where(cum_acc >= target_selective_accuracy)[0]
    target_met = True
    if len(meets) > 0:
        # the largest prefix (lowest threshold) whose selective accuracy meets target
        k = int(meets.max())
        confident_t = float(conf_sorted[k])
    else:
        target_met = False
        min_k = max(1, int(np.ceil(0.05 * n))) - 1
        k = int(np.argmax(cum_acc[min_k:]) + min_k)
        confident_t = float(conf_sorted[k])
        notes.append(
            f"Selective-accuracy target {target_selective_accuracy:.0%} not reachable on the "
            f"{selection_split} split; using the best achievable threshold.")

    # --- reject threshold ---
    reject_t = confident_t
    if (conf < confident_t).any():
        asc = np.argsort(conf, kind="stable")
        local = isotonic_increasing(in_topk[asc].astype(np.float64))
        ok = np.where((local >= target_candidate_topk_accuracy) & (conf[asc] < confident_t))[0]
        if len(ok) > 0:
            reject_t = float(conf[asc][int(ok.min())])
        else:
            notes.append("The candidate shortlist never reaches the top-k target below the confident "
                         "threshold; every prediction below it will be reported as inconclusive.")

    confident_mask = conf >= confident_t
    uncertain_mask = (conf >= reject_t) & ~confident_mask
    rejected_mask = conf < reject_t
    return ThresholdSelection(
        confident_threshold=confident_t,
        reject_threshold=reject_t,
        target_selective_accuracy=target_selective_accuracy,
        target_candidate_topk_accuracy=target_candidate_topk_accuracy,
        candidate_top_k=top_k,
        selection_split=selection_split,
        selection_n=n,
        confident_coverage=float(confident_mask.mean()),
        confident_accuracy=float(correct[confident_mask].mean()) if confident_mask.any() else None,
        uncertain_coverage=float(uncertain_mask.mean()),
        uncertain_topk_accuracy=float(in_topk[uncertain_mask].mean()) if uncertain_mask.any() else None,
        rejected_coverage=float(rejected_mask.mean()),
        target_met=target_met,
        notes=notes,
        reject_method="isotonic_local_topk",
    )


def evaluate_thresholds(probs: np.ndarray, labels: np.ndarray, confident_t: float,
                        reject_t: float, top_k: int = 3) -> Dict[str, Optional[float]]:
    """Apply already-selected thresholds to another split (e.g. TEST) and report
    what they achieve there — the honest, held-out number."""
    conf = probs.max(axis=1)
    correct = probs.argmax(axis=1) == labels
    topk_idx = np.argsort(-probs, axis=1)[:, :top_k]
    in_topk = (topk_idx == labels[:, None]).any(axis=1)
    confident = conf >= confident_t
    uncertain = (conf >= reject_t) & ~confident
    rejected = conf < reject_t

    def _mean(arr, mask):
        return float(arr[mask].mean()) if mask.any() else None

    return {
        "n": int(len(labels)),
        "confident_coverage": float(confident.mean()),
        "confident_accuracy": _mean(correct, confident),
        "uncertain_coverage": float(uncertain.mean()),
        "uncertain_top1_accuracy": _mean(correct, uncertain),
        "uncertain_topk_accuracy": _mean(in_topk, uncertain),
        "rejected_coverage": float(rejected.mean()),
        "rejected_top1_accuracy_if_forced": _mean(correct, rejected),
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
@dataclass
class CalibrationArtifact:
    temperature: float
    thresholds: ThresholdSelection
    plant_mass_threshold: Optional[float]
    validation_metrics_before: Dict[str, float]
    validation_metrics_after: Dict[str, float]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema_version: int = CALIBRATION_SCHEMA_VERSION
    method: str = "temperature_scaling"

    def save(self, run_dir: Path) -> Path:
        path = run_dir / CALIBRATION_FILENAME
        payload = asdict(self)
        path.write_text(json.dumps(payload, indent=2))
        return path

    @classmethod
    def load(cls, run_dir: Path) -> Optional["CalibrationArtifact"]:
        path = run_dir / CALIBRATION_FILENAME
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        thresholds = ThresholdSelection(**data["thresholds"])
        return cls(
            temperature=float(data["temperature"]),
            thresholds=thresholds,
            plant_mass_threshold=data.get("plant_mass_threshold"),
            validation_metrics_before=data.get("validation_metrics_before", {}),
            validation_metrics_after=data.get("validation_metrics_after", {}),
            created_at=data.get("created_at", ""),
            schema_version=int(data.get("schema_version", 1)),
            method=data.get("method", "temperature_scaling"),
        )


def calibration_metrics(probs: np.ndarray, labels: np.ndarray, n_bins: int = 15) -> Dict[str, float]:
    ece = expected_calibration_error(probs, labels, n_bins)
    return {
        "nll": negative_log_likelihood(probs, labels),
        "brier": brier_score(probs, labels),
        "ece": ece["ece"],
        "mce": ece["mce"],
        "accuracy": float((probs.argmax(axis=1) == labels).mean()),
        "mean_confidence": float(probs.max(axis=1).mean()),
    }
