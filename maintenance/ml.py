"""Isolation Forest estimator with explicit feature/version and score contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from sklearn.ensemble import IsolationForest

from .features import FEATURE_NAMES, WINDOW_SIZE, extract_features, feature_rows
from .health import HealthScorer, SensorPoint
from .telemetry import SCENARIOS, generate_sequence

DEFAULT_MODEL = Path(__file__).resolve().parents[1] / "models/machine_health_iforest.joblib"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class HealthPrediction:
    machine_id: str
    health_score: float
    anomaly_score: float
    status: str
    source: str
    reasons: list[str]
    recommendation: str
    sample_count: int

    def to_dict(self) -> dict:
        return asdict(self)


def health_status(anomaly: float) -> str:
    if not np.isfinite(anomaly) or not 0 <= anomaly <= 1:
        raise ValueError("Normalized anomaly must be in [0, 1]")
    return (
        "critical"
        if anomaly >= 0.8
        else "degrading"
        if anomaly >= 0.5
        else "watch"
        if anomaly >= 0.2
        else "healthy"
    )


def rule_prediction(history: list[SensorPoint], reason: str | None = None) -> HealthPrediction:
    if not history:
        raise ValueError("At least one telemetry sample is required")
    extract_features(history)  # Validate even during warmup.
    result = HealthScorer().recommend(history[-1])
    return HealthPrediction(
        result.machine_id,
        result.health_score,
        round(1 - result.health_score, 3),
        "degrading" if result.status == "warning" else result.status,
        "rules",
        result.reasons + ([reason] if reason else []),
        result.recommendation,
        len(history),
    )


class MLHealthEstimator:
    def __init__(self, model: IsolationForest, metadata: dict) -> None:
        self.model, self.metadata = model, metadata
        self.window = metadata["window_size"]

    def scores(self, rows: np.ndarray) -> np.ndarray:
        raw = -self.model.score_samples(rows)
        scale = self.metadata["normalization"]
        return np.clip((raw - scale["healthy_reference"]) / scale["span"], 0, 1)

    def predict(self, history: list[SensorPoint]) -> HealthPrediction:
        row = extract_features(history, self.window)
        if row is None:
            return rule_prediction(
                history, f"ML warmup: {len(history)}/{self.window} samples; rule fallback"
            )
        anomaly = float(self.scores(row.reshape(1, -1))[0])
        status = health_status(anomaly)
        # Signal deltas are descriptive evidence, not model feature attribution.
        reasons = [
            f"Isolation Forest normalized anomaly {anomaly:.3f}",
            "Signal deviations are descriptive, not causal diagnosis",
        ]
        for i, signal in enumerate(("temperature", "vibration", "current")):
            reasons.append(f"{signal} mean={row[3 + i]:.3f}, slope/sample={row[9 + i]:.3f}")
        recommendation = (
            "No maintenance action required."
            if status == "healthy"
            else "Inspect telemetry and prefer a lower-risk compatible station."
        )
        return HealthPrediction(
            history[-1].machine_id,
            round(1 - anomaly, 4),
            round(anomaly, 4),
            status,
            "ml_isolation_forest",
            reasons,
            recommendation,
            min(len(history), self.window),
        )

    def save(self, path: str | Path = DEFAULT_MODEL) -> None:
        import joblib

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, path, compress=3)
        metadata = {**self.metadata, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        path.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path = DEFAULT_MODEL) -> MLHealthEstimator:
        path = Path(path)
        try:
            import joblib
            import sklearn
            from sklearn.ensemble import IsolationForest

            metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
            valid = (
                metadata["schema_version"] == SCHEMA_VERSION
                and metadata["model_type"] == "IsolationForest"
                and metadata["model_version"] == "1.0"
                and metadata["feature_names"] == list(FEATURE_NAMES)
                and metadata["window_size"] == WINDOW_SIZE
                and metadata["sklearn_version"] == sklearn.__version__
                and np.isfinite(metadata["normalization"]["span"])
                and metadata["normalization"]["span"] >= 0.02
                and np.isfinite(metadata["normalization"]["healthy_reference"])
                and metadata["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
            )
            if not valid:
                raise ValueError("Incompatible model metadata or checksum")
            # Only load artifacts trained locally or from a trusted source; joblib is executable.
            model = joblib.load(path)
            if not isinstance(model, IsolationForest) or model.n_features_in_ != len(
                FEATURE_NAMES
            ):
                raise ValueError("Incompatible estimator")
            return cls(model, metadata)
        except (ImportError, OSError, KeyError, TypeError, ValueError, EOFError) as exc:
            raise ValueError(
                f"ML health model unavailable/incompatible at {path}; run scripts/train_health_model.py"
            ) from exc


def train_model(seed: int = 42) -> MLHealthEstimator:
    import sklearn
    from sklearn.ensemble import IsolationForest

    # Whole sequences have disjoint seeds; no overlapping train/test windows.
    rows = np.concatenate([feature_rows(generate_sequence(seed=seed + i)) for i in range(24)])
    calibration = np.concatenate(
        [feature_rows(generate_sequence(seed=seed + 1000 + i)) for i in range(8)]
    )
    parameters = {
        "n_estimators": 128,
        "max_samples": 256,
        "contamination": "auto",
        "random_state": seed,
        "n_jobs": 1,
    }
    model = IsolationForest(**parameters).fit(rows)
    calibration_scores = -model.score_samples(calibration)
    reference = float(np.quantile(calibration_scores, 0.95))
    # Set the alert boundary from healthy calibration only, not defect labels.
    span = max(0.02, 2 * (float(np.quantile(calibration_scores, 0.995)) - reference))
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "model_version": "1.0",
        "model_type": "IsolationForest",
        "status_thresholds": {"watch": 0.2, "degrading": 0.5, "critical": 0.8},
        "feature_names": list(FEATURE_NAMES),
        "window_size": WINDOW_SIZE,
        "training_seed": seed,
        "sklearn_version": sklearn.__version__,
        "parameters": parameters,
        "training_windows": len(rows),
        "calibration_windows": len(calibration),
        "normalization": {
            "healthy_reference": reference,
            "span": span,
            "method": "healthy q95 to q99.5; anomaly 0.5 at q99.5, minimum span 0.02",
        },
        "score_semantics": "normalized anomaly, not probability; health = 1 - anomaly",
    }
    return MLHealthEstimator(model, metadata)


def evaluate_model(estimator: MLHealthEstimator) -> dict:
    seed = estimator.metadata["training_seed"] + 10000
    healthy = np.concatenate(
        [estimator.scores(feature_rows(generate_sequence(seed=seed + i))) for i in range(8)]
    )
    degraded = {}
    for scenario in SCENARIOS[1:]:
        # Report late, clearly degraded windows, not the healthy prelude as defects.
        degraded[scenario] = np.concatenate(
            [
                estimator.scores(
                    feature_rows(generate_sequence(seed=seed + i, scenario=scenario))
                )[-40:]
                for i in range(8)
            ]
        )
    abnormal = np.concatenate(list(degraded.values()))
    tp, fp, fn = (
        int((abnormal >= 0.5).sum()),
        int((healthy >= 0.5).sum()),
        int((abnormal < 0.5).sum()),
    )
    return {
        "healthy_windows": len(healthy),
        "degraded_windows": len(abnormal),
        "definition": "8 held-out sequences/scenario; healthy all windows, degraded last 40 windows; anomaly >= 0.5",
        "healthy_false_positive_rate": float(np.mean(healthy >= 0.5)),
        "degraded_detection_rate": float(np.mean(abnormal >= 0.5)),
        "mean_healthy_anomaly": float(healthy.mean()),
        "mean_degraded_anomaly": float(abnormal.mean()),
        "precision": tp / max(1, tp + fp),
        "recall": tp / max(1, tp + fn),
        "f1": 2 * tp / max(1, 2 * tp + fp + fn),
        "scenario_detection_rates": {k: float(np.mean(v >= 0.5)) for k, v in degraded.items()},
    }
