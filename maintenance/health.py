"""Rule-based predictive-maintenance baseline."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean


@dataclass(frozen=True)
class SensorPoint:
    machine_id: str
    temperature_c: float
    vibration_mm_s: float
    current_a: float
    timestamp: str | None = None


@dataclass(frozen=True)
class MaintenanceRecommendation:
    machine_id: str
    health_score: float
    status: str
    recommendation: str
    reasons: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "machine_id": self.machine_id,
            "health_score": self.health_score,
            "status": self.status,
            "recommendation": self.recommendation,
            "reasons": list(self.reasons),
        }


class HealthScorer:
    """Conservative baseline scorer before ML is introduced."""

    def __init__(
        self,
        *,
        nominal_temperature_c: float = 35.0,
        max_temperature_c: float = 90.0,
        nominal_vibration_mm_s: float = 0.1,
        max_vibration_mm_s: float = 4.0,
        nominal_current_a: float = 0.8,
        max_current_a: float = 3.0,
    ) -> None:
        self.nominal_temperature_c = nominal_temperature_c
        self.max_temperature_c = max_temperature_c
        self.nominal_vibration_mm_s = nominal_vibration_mm_s
        self.max_vibration_mm_s = max_vibration_mm_s
        self.nominal_current_a = nominal_current_a
        self.max_current_a = max_current_a

    def score(self, point: SensorPoint) -> float:
        penalties = [
            self._ratio(
                point.temperature_c,
                self.nominal_temperature_c,
                self.max_temperature_c,
            ),
            self._ratio(
                point.vibration_mm_s,
                self.nominal_vibration_mm_s,
                self.max_vibration_mm_s,
            ),
            self._ratio(point.current_a, self.nominal_current_a, self.max_current_a),
        ]
        health = 1.0 - mean(penalties)
        return round(max(0.0, min(1.0, health)), 3)

    def recommend(self, point: SensorPoint) -> MaintenanceRecommendation:
        health = self.score(point)
        reasons: list[str] = []
        if point.temperature_c >= 70:
            reasons.append("temperature trending high")
        if point.vibration_mm_s >= 2.5:
            reasons.append("vibration trending high")
        if point.current_a >= 2.2:
            reasons.append("current draw trending high")

        if health < 0.35:
            status = "critical"
            recommendation = "Schedule immediate maintenance before running more work."
        elif health < 0.6:
            status = "warning"
            recommendation = "Plan maintenance and reduce workload if possible."
        elif health < 0.8:
            status = "watch"
            recommendation = "Monitor trend and inspect during the next planned stop."
        else:
            status = "healthy"
            recommendation = "No maintenance action required."

        if not reasons:
            reasons.append("sensor values are within baseline range")

        return MaintenanceRecommendation(
            machine_id=point.machine_id,
            health_score=health,
            status=status,
            recommendation=recommendation,
            reasons=reasons,
        )

    @staticmethod
    def _ratio(value: float, nominal: float, maximum: float) -> float:
        if value <= nominal:
            return 0.0
        return max(0.0, min(1.0, (value - nominal) / (maximum - nominal)))


def detect_degradation_trend(points: list[SensorPoint], window: int = 5) -> dict[str, object]:
    if len(points) < max(2, window):
        return {
            "trend": "insufficient_data",
            "temperature_slope": 0.0,
            "vibration_slope": 0.0,
        }
    recent = points[-window:]
    older = points[-(window * 2) : -window] if len(points) >= window * 2 else points[:-window]
    if not older:
        older = points[:1]
    temperature_slope = mean(p.temperature_c for p in recent) - mean(
        p.temperature_c for p in older
    )
    vibration_slope = mean(p.vibration_mm_s for p in recent) - mean(
        p.vibration_mm_s for p in older
    )
    trend = "degrading" if temperature_slope > 3.0 or vibration_slope > 0.4 else "stable"
    return {
        "trend": trend,
        "temperature_slope": round(temperature_slope, 3),
        "vibration_slope": round(vibration_slope, 3),
    }
