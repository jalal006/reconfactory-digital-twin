"""Bounded online history, with explicit rule fallback during ML warmup."""

from collections import deque

from .features import WINDOW_SIZE
from .health import SensorPoint
from .ml import DEFAULT_MODEL, MLHealthEstimator, rule_prediction


class HealthMonitor:
    def __init__(self, mode: str = "rules", model_path=DEFAULT_MODEL) -> None:
        if mode not in {"rules", "ml"}:
            raise ValueError("MAINTENANCE_MODE must be rules or ml")
        self.mode = mode
        self.estimator = MLHealthEstimator.load(model_path) if mode == "ml" else None
        self.histories: dict[str, deque] = {}

    def observe(self, point: SensorPoint):
        history = self.histories.setdefault(point.machine_id, deque(maxlen=WINDOW_SIZE))
        # Validate before inserting, so an invalid reading cannot poison the window.
        rule_prediction([point])
        history.append(point)
        return (
            self.estimator.predict(list(history))
            if self.estimator
            else rule_prediction(list(history))
        )
