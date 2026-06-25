"""Shared domain models for the ReConFactory simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return utc_now().isoformat()


class MachineState(str, Enum):
    OFFLINE = "offline"
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    BLOCKED = "blocked"
    FAULT = "fault"
    MAINTENANCE = "maintenance"
    RECOVERING = "recovering"
    EMERGENCY_STOP = "emergency_stop"


class ProductStatus(str, Enum):
    WAITING = "waiting"
    QUEUED = "queued"
    IN_TRANSIT = "in_transit"
    PROCESSING = "processing"
    PAUSED = "paused"
    COMPLETED = "completed"
    REJECTED = "rejected"


class QualityStatus(str, Enum):
    UNKNOWN = "unknown"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class FaultType(str, Enum):
    OVERHEAT = "overheat"
    JAM = "jam"
    SENSOR_FAILURE = "sensor_failure"
    CAMERA_FAILURE = "camera_failure"
    TIMEOUT = "timeout"
    COMMUNICATION_LOSS = "communication_loss"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ProductRecipe:
    product_type: str
    display_name: str
    required_processes: list[str]
    inspection_rule: str
    color: str
    shape: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_type": self.product_type,
            "display_name": self.display_name,
            "required_processes": list(self.required_processes),
            "inspection_rule": self.inspection_rule,
            "color": self.color,
            "shape": self.shape,
        }


@dataclass
class Product:
    product_id: str
    product_type: str
    display_name: str
    required_processes: list[str]
    current_location: str = "input_queue"
    status: ProductStatus = ProductStatus.WAITING
    quality: QualityStatus = QualityStatus.UNKNOWN
    assigned_station: str | None = None
    completed_processes: list[str] = field(default_factory=list)
    route: list[str] = field(default_factory=lambda: ["input_queue"])
    defect_flags: list[str] = field(default_factory=list)
    inspection_confidence: float = 0.0
    defect_reason: str | None = None
    recovery_notes: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=iso_now)
    updated_at: str = field(default_factory=iso_now)

    def mark_updated(self) -> None:
        self.updated_at = iso_now()

    def next_process(self) -> str | None:
        for process in self.required_processes:
            if process not in self.completed_processes:
                return process
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "product_type": self.product_type,
            "display_name": self.display_name,
            "required_processes": list(self.required_processes),
            "completed_processes": list(self.completed_processes),
            "next_process": self.next_process(),
            "current_location": self.current_location,
            "status": self.status.value,
            "quality": self.quality.value,
            "assigned_station": self.assigned_station,
            "route": list(self.route),
            "defect_flags": list(self.defect_flags),
            "inspection_confidence": self.inspection_confidence,
            "defect_reason": self.defect_reason,
            "recovery_notes": list(self.recovery_notes),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class MachineConfig:
    machine_id: str
    name: str
    machine_type: str
    capabilities: list[str]
    processing_time: dict[str, int]
    input_location: str
    output_location: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "machine_id": self.machine_id,
            "name": self.name,
            "machine_type": self.machine_type,
            "capabilities": list(self.capabilities),
            "processing_time": dict(self.processing_time),
            "input_location": self.input_location,
            "output_location": self.output_location,
        }


@dataclass
class SensorSnapshot:
    machine_id: str
    temperature_c: float = 34.0
    vibration_mm_s: float = 0.08
    current_a: float = 1.0
    jammed: bool = False
    sensor_ok: bool = True
    camera_ok: bool = True
    heartbeat_age_s: float = 0.0
    process_runtime_s: float = 0.0
    timestamp: str = field(default_factory=iso_now)

    def update_timestamp(self) -> None:
        self.timestamp = iso_now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "machine_id": self.machine_id,
            "temperature_c": round(self.temperature_c, 2),
            "vibration_mm_s": round(self.vibration_mm_s, 3),
            "current_a": round(self.current_a, 2),
            "jammed": self.jammed,
            "sensor_ok": self.sensor_ok,
            "camera_ok": self.camera_ok,
            "heartbeat_age_s": round(self.heartbeat_age_s, 2),
            "process_runtime_s": round(self.process_runtime_s, 2),
            "timestamp": self.timestamp,
        }


@dataclass
class MachineStatus:
    machine_id: str
    name: str
    machine_type: str
    state: MachineState
    capabilities: list[str]
    current_product_id: str | None
    current_process: str | None
    remaining_ticks: int
    healthy: bool
    unavailable_reason: str | None
    sensors: SensorSnapshot
    cycle_count: int
    downtime_ticks: int
    utilization_ticks: int
    health_score: float
    maintenance_status: str
    maintenance_recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "machine_id": self.machine_id,
            "name": self.name,
            "machine_type": self.machine_type,
            "state": self.state.value,
            "capabilities": list(self.capabilities),
            "current_product_id": self.current_product_id,
            "current_process": self.current_process,
            "remaining_ticks": self.remaining_ticks,
            "healthy": self.healthy,
            "unavailable_reason": self.unavailable_reason,
            "sensors": self.sensors.to_dict(),
            "cycle_count": self.cycle_count,
            "downtime_ticks": self.downtime_ticks,
            "utilization_ticks": self.utilization_ticks,
            "health_score": self.health_score,
            "maintenance_status": self.maintenance_status,
            "maintenance_recommendation": self.maintenance_recommendation,
        }


@dataclass
class FactoryEvent:
    event_type: str
    message: str
    source: str = "factory"
    severity: Severity = Severity.INFO
    data: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: f"E-{uuid4().hex[:10].upper()}")
    timestamp: str = field(default_factory=iso_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "message": self.message,
            "source": self.source,
            "severity": self.severity.value,
            "data": dict(self.data),
            "timestamp": self.timestamp,
        }


@dataclass
class FaultRecord:
    fault_id: str
    machine_id: str
    fault_type: FaultType
    severity: Severity
    likely_cause: str
    recommendation: str
    explanation: str
    evidence: dict[str, Any] = field(default_factory=dict)
    detected_at: str = field(default_factory=iso_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fault_id": self.fault_id,
            "machine_id": self.machine_id,
            "fault_type": self.fault_type.value,
            "severity": self.severity.value,
            "likely_cause": self.likely_cause,
            "recommendation": self.recommendation,
            "explanation": self.explanation,
            "evidence": dict(self.evidence),
            "detected_at": self.detected_at,
        }


@dataclass
class RecoveryAction:
    action_id: str
    fault_id: str
    machine_id: str
    action_type: str
    rerouted_products: list[str] = field(default_factory=list)
    paused_products: list[str] = field(default_factory=list)
    explanation: str = ""
    created_at: str = field(default_factory=iso_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "fault_id": self.fault_id,
            "machine_id": self.machine_id,
            "action_type": self.action_type,
            "rerouted_products": list(self.rerouted_products),
            "paused_products": list(self.paused_products),
            "explanation": self.explanation,
            "created_at": self.created_at,
        }
