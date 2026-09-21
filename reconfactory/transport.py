"""ROS-independent contracts and state transitions for one AMR."""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from .models import iso_now

TERMINAL = {"delivered", "failed", "cancelled"}
TRANSITIONS = {
    "requested": {"accepted", "failed", "cancelled"},
    "accepted": {"navigating", "failed", "cancelled"},
    "navigating": {"delivered", "failed", "cancelled"},
}


def task_timeout_s() -> float:
    value = float(os.getenv("AMR_TASK_TIMEOUT_S", "300"))
    if not math.isfinite(value) or value <= 0:
        raise ValueError("AMR_TASK_TIMEOUT_S must be finite and positive")
    return value


def load_station_goals(path: str | Path) -> dict[str, dict[str, float]]:
    stations = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["stations"]
    result = {}
    for name, pose in stations.items():
        values = {key: float(pose[key]) for key in ("x", "y", "yaw")}
        if not all(math.isfinite(value) for value in values.values()):
            raise ValueError(f"Non-finite station pose: {name}")
        result[str(name)] = values
    return result


@dataclass
class TransportRequest:
    product_id: str
    origin: str
    destination: str
    task_id: str = field(default_factory=lambda: f"T-{uuid4().hex}")
    requested_at: str = field(default_factory=iso_now)
    robot_id: str = "amr_01"
    status: str = "requested"
    phase: str = "pickup"
    started_at: str | None = None
    completed_at: str | None = None
    navigation_time_s: float = 0.0
    failure_reason: str | None = None
    cancel_requested: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any], stations: dict) -> TransportRequest:
        for key in ("task_id", "product_id", "origin", "destination"):
            if not isinstance(data.get(key), str) or not data[key].strip():
                raise ValueError(f"Missing transport {key}")
        if data["origin"] not in stations or data["destination"] not in stations:
            raise ValueError("Unknown origin or destination station")
        return cls(
            **{key: data[key] for key in ("task_id", "product_id", "origin", "destination")}
        )

    def update(self, payload: dict[str, Any]) -> bool:
        if any(
            payload.get(key) != getattr(self, key)
            for key in ("task_id", "product_id", "destination")
        ):
            raise ValueError("Transport result does not match the active task")
        status = payload.get("status")
        if self.status in TERMINAL:
            return False
        if self.cancel_requested and status == "delivered":
            raise ValueError("Delivery refused after cancellation was requested")
        phase_advanced = (
            status == self.status == "navigating"
            and self.phase == "pickup"
            and payload.get("phase") == "delivery"
        )
        if status == self.status and not phase_advanced:
            return False
        if not phase_advanced and status not in TRANSITIONS.get(self.status, set()):
            raise ValueError(f"Invalid transport transition: {self.status} -> {status}")
        if payload.get("phase", self.phase) not in {"pickup", "delivery"}:
            raise ValueError("Invalid transport phase")
        if payload.get("phase", self.phase) != self.phase and not phase_advanced:
            raise ValueError("Transport phase cannot skip or reverse pickup")
        if status == "delivered" and self.phase != "delivery":
            raise ValueError("Delivery requires successful pickup first")
        elapsed = float(payload.get("navigation_time_s", 0.0))
        if not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("Invalid navigation time")
        self.status = status
        self.phase = str(payload.get("phase", self.phase))
        if status == "navigating" and self.started_at is None:
            self.started_at = iso_now()
        if status in TERMINAL:
            self.completed_at = iso_now()
        self.navigation_time_s = elapsed
        self.failure_reason = payload.get("failure_reason")
        return True


class TaskRegistry:
    """Reject replays and concurrent work; navigation remains external."""

    def __init__(self, stations: dict) -> None:
        self.stations = stations
        self.seen: set[str] = set()
        self.active: TransportRequest | None = None

    def receive(self, payload: dict) -> TransportRequest:
        request = TransportRequest.from_dict(payload, self.stations)
        if request.task_id in self.seen:
            raise ValueError("Duplicate task ID")
        if self.active and self.active.status not in TERMINAL:
            raise ValueError("AMR is busy")
        self.seen.add(request.task_id)
        self.active = request
        return request
