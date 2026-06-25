"""Station-selection logic for product recipes."""

from __future__ import annotations

from .models import Product
from .stations import StationController


class ProductionScheduler:
    def __init__(
        self,
        stations: dict[str, StationController],
        routing_weights: dict[str, float] | None = None,
    ) -> None:
        self.stations = stations
        self.routing_weights = routing_weights or {}

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
    ) -> StationController | None:
        candidates = [
            station
            for station in self.compatible_stations(process, machine_type)
            if station.can_accept(process)
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

        return min(candidates, key=score)
