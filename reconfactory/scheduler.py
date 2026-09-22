"""Station-selection logic for product recipes."""

from __future__ import annotations

from .models import Product
from .stations import StationController


class ProductionScheduler:
    def __init__(
        self,
        stations: dict[str, StationController],
        routing_weights: dict[str, float] | None = None,
        health_policy: dict | None = None,
    ) -> None:
        self.stations = stations
        self.routing_weights = routing_weights or {}
        self.health_policy = health_policy or {}
        self.last_health_decision: dict | None = None

    def compatible_stations(
        self, process: str, machine_type: str | None = None
    ) -> list[StationController]:
        stations = [
            station
            for station in self.stations.values()
            if process in station.config.capabilities
        ]
        if machine_type:
            stations = [
                station for station in stations if station.config.machine_type == machine_type
            ]
        return stations

    def healthy_supported(self, process: str, machine_type: str | None = None) -> bool:
        return any(
            station.healthy for station in self.compatible_stations(process, machine_type)
        )

    def select_station(
        self,
        product: Product,
        process: str,
        machine_type: str | None = "processing",
        excluded: set[str] | None = None,
    ) -> StationController | None:
        self.last_health_decision = None
        candidates = [
            station
            for station in self.compatible_stations(process, machine_type)
            if station.can_accept(process) and station.machine_id not in (excluded or set())
        ]
        if not candidates:
            return None

        def score(station: StationController) -> float:
            processing_time_weight = self.routing_weights.get("processing_time", 1.0)
            utilization_weight = self.routing_weights.get("utilization", 0.15)
            station_preference = self.routing_weights.get(
                f"{station.machine_id}_preference", 0.0
            )
            return (
                station.processing_time_for(process) * processing_time_weight
                + station.utilization_ticks * utilization_weight
                + station_preference
            )

        baseline = min(candidates, key=score)
        if not self.health_policy.get("enabled", False) or machine_type != "processing":
            return baseline

        def penalty(station: StationController) -> float:
            prediction = station.health_prediction
            status = prediction.status if prediction else "healthy"
            return float(self.health_policy.get(f"{status}_penalty", 0.0))

        eligible = [
            s
            for s in candidates
            if not (
                self.health_policy.get("critical_exclusion", True)
                and s.health_prediction
                and s.health_prediction.status == "critical"
            )
        ]
        if not eligible:
            return None
        selected = min(eligible, key=lambda s: score(s) + penalty(s))
        if selected != baseline:
            avoided = baseline.health_prediction
            chosen = selected.health_prediction
            self.last_health_decision = {
                "product_id": product.product_id,
                "operation": process,
                "avoided_machine": baseline.machine_id,
                "selected_machine": selected.machine_id,
                "avoided_health_score": avoided.health_score if avoided else 1.0,
                "selected_health_score": chosen.health_score if chosen else 1.0,
                "avoided_anomaly_score": avoided.anomaly_score if avoided else 0.0,
                "source": avoided.source if avoided else "rules",
                "reason": f"{baseline.config.name} predictive-health risk; selected {selected.config.name}",
            }
        return selected
