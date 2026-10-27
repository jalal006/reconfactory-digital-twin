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
        return self.observe_many([point])[0]

    def observe_many(self, points: list[SensorPoint]):
        return self.predict_histories(self.record_many(points))

    def record_many(self, points: list[SensorPoint]):
        # Validate the whole batch before mutating any station history.
        for point in points:
            rule_prediction([point])
        return [self._append(point) for point in points]

    def predict_histories(self, histories):
        # Histories are detached lists: inference can run outside the API loop.
        return (
            self.estimator.predict_many(histories)
            if self.estimator
            else [rule_prediction(history) for history in histories]
        )

    def _append(self, point):
        history = self.histories.setdefault(point.machine_id, deque(maxlen=WINDOW_SIZE))
        history.append(point)
        return list(history)
