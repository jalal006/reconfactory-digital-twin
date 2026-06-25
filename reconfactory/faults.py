"""Fault detection and diagnosis."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from .models import FaultRecord, FaultType, MachineState, Severity
from .stations import StationController


@dataclass(frozen=True)
class DetectedFault:
    machine_id: str
    fault_type: FaultType
    message: str


class FaultDetector:
    def __init__(self, rules: dict[str, float | int]) -> None:
        self.rules = rules

    def evaluate(self, stations: dict[str, StationController]) -> list[DetectedFault]:
        detected: list[DetectedFault] = []
        temperature_limit = float(self.rules["temperature_limit_c"])
        heartbeat_timeout = float(self.rules["heartbeat_timeout_s"])
        process_timeout = float(self.rules["process_timeout_ticks"])
        vibration_limit = float(self.rules["vibration_limit_mm_s"])
        for station in stations.values():
            if station.state == MachineState.FAULT:
                continue
            sensors = station.sensors
            if sensors.temperature_c >= temperature_limit:
                detected.append(
                    DetectedFault(
                        station.machine_id,
                        FaultType.OVERHEAT,
                        f"{station.config.name} exceeded {temperature_limit:.1f} C",
                    )
                )
            elif sensors.jammed:
                detected.append(
                    DetectedFault(
                        station.machine_id,
                        FaultType.JAM,
                        f"{station.config.name} reported a jam",
                    )
                )
            elif not sensors.sensor_ok:
                detected.append(
                    DetectedFault(
                        station.machine_id,
                        FaultType.SENSOR_FAILURE,
                        f"{station.config.name} sensor signal is invalid",
                    )
                )
            elif station.config.machine_type == "inspection" and not sensors.camera_ok:
                detected.append(
                    DetectedFault(
                        station.machine_id,
                        FaultType.CAMERA_FAILURE,
                        f"{station.config.name} camera feed is unavailable",
                    )
                )
            elif sensors.heartbeat_age_s >= heartbeat_timeout:
                detected.append(
                    DetectedFault(
                        station.machine_id,
                        FaultType.COMMUNICATION_LOSS,
                        f"{station.config.name} heartbeat timed out",
                    )
                )
            elif (
                sensors.process_runtime_s > process_timeout
                or sensors.vibration_mm_s > vibration_limit
            ):
                detected.append(
                    DetectedFault(
                        station.machine_id,
                        FaultType.TIMEOUT,
                        f"{station.config.name} operation exceeded normal runtime",
                    )
                )
        return detected


class DiagnosisEngine:
    def diagnose(self, station: StationController, fault_type: FaultType) -> FaultRecord:
        sensors = station.sensors
        evidence = {
            "temperature_c": round(sensors.temperature_c, 2),
            "vibration_mm_s": round(sensors.vibration_mm_s, 3),
            "current_a": round(sensors.current_a, 2),
            "jammed": sensors.jammed,
            "sensor_ok": sensors.sensor_ok,
            "camera_ok": sensors.camera_ok,
            "heartbeat_age_s": round(sensors.heartbeat_age_s, 2),
            "process_runtime_s": round(sensors.process_runtime_s, 2),
        }
        explanations = {
            FaultType.OVERHEAT: (
                Severity.HIGH,
                "Excess temperature",
                "Stop assigning new work, cool the station, and inspect load or tooling.",
                "Temperature crossed the safe threshold, so the station was removed from scheduling.",
            ),
            FaultType.JAM: (
                Severity.HIGH,
                "Mechanical blockage or conveyor jam",
                "Stop upstream movement, clear the blockage, then recover the machine.",
                "A jam flag was reported, so products are held until the path is safe.",
            ),
            FaultType.SENSOR_FAILURE: (
                Severity.WARNING,
                "Sensor signal failure",
                "Validate wiring or simulated sensor source before allowing production.",
                "The controller received an invalid sensor status from the equipment.",
            ),
            FaultType.CAMERA_FAILURE: (
                Severity.WARNING,
                "Camera stream unavailable",
                "Restore the camera or send unidentified products to the reject path.",
                "Vision inspection cannot validate product identity without the camera feed.",
            ),
            FaultType.TIMEOUT: (
                Severity.HIGH,
                "Processing time anomaly",
                "Inspect the station for stuck workpieces, worn tooling, or stalled motors.",
                "The operation took longer than the configured safe runtime.",
            ),
            FaultType.COMMUNICATION_LOSS: (
                Severity.CRITICAL,
                "Controller heartbeat lost",
                "Place the machine in a safe state and restore communication.",
                "The heartbeat age exceeded the configured timeout.",
            ),
            FaultType.UNKNOWN: (
                Severity.WARNING,
                "Unclassified fault",
                "Inspect the station manually.",
                "The station was marked unavailable by an unknown trigger.",
            ),
        }
        severity, cause, recommendation, explanation = explanations[fault_type]
        return FaultRecord(
            fault_id=f"F-{uuid4().hex[:10].upper()}",
            machine_id=station.machine_id,
            fault_type=fault_type,
            severity=severity,
            likely_cause=cause,
            recommendation=recommendation,
            explanation=explanation,
            evidence=evidence,
        )
