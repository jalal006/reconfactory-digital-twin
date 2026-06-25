"""Station and conveyor controllers."""

from __future__ import annotations

from dataclasses import dataclass

from maintenance import HealthScorer, SensorPoint

from .models import FaultType, MachineConfig, MachineState, MachineStatus, SensorSnapshot
from .state_machine import MachineStateMachine


@dataclass(frozen=True)
class CompletedOperation:
    machine_id: str
    product_id: str
    process: str


class StationController:
    def __init__(self, config: MachineConfig) -> None:
        self.config = config
        self.machine = MachineStateMachine()
        self.sensors = SensorSnapshot(machine_id=config.machine_id)
        self.current_product_id: str | None = None
        self.current_process: str | None = None
        self.remaining_ticks = 0
        self.cycle_count = 0
        self.downtime_ticks = 0
        self.utilization_ticks = 0
        self.unavailable_reason: str | None = None
        self.health_scorer = HealthScorer()

    @property
    def machine_id(self) -> str:
        return self.config.machine_id

    @property
    def state(self) -> MachineState:
        return self.machine.state

    @property
    def healthy(self) -> bool:
        if self.state in {
            MachineState.OFFLINE,
            MachineState.FAULT,
            MachineState.MAINTENANCE,
            MachineState.EMERGENCY_STOP,
        }:
            return False
        return self.sensors.sensor_ok and not self.sensors.jammed and self.sensors.camera_ok

    def start(self) -> None:
        if self.state == MachineState.OFFLINE:
            self.machine.transition(MachineState.STARTING)
            self.machine.transition(MachineState.IDLE)
        elif self.state == MachineState.RECOVERING:
            self.machine.transition(MachineState.IDLE)

    def can_accept(self, process: str) -> bool:
        return (
            process in self.config.capabilities
            and self.state == MachineState.IDLE
            and self.healthy
            and self.current_product_id is None
        )

    def processing_time_for(self, process: str) -> int:
        return max(1, int(self.config.processing_time.get(process, 2)))

    def assign(self, product_id: str, process: str) -> None:
        if not self.can_accept(process):
            raise ValueError(f"{self.machine_id} cannot accept {process}")
        self.current_product_id = product_id
        self.current_process = process
        self.remaining_ticks = self.processing_time_for(process)
        self.sensors.process_runtime_s = 0
        self.machine.transition(MachineState.RUNNING)

    def tick(self) -> CompletedOperation | None:
        self.sensors.heartbeat_age_s = 0
        self.sensors.update_timestamp()
        if self.state == MachineState.RUNNING:
            self.remaining_ticks -= 1
            self.utilization_ticks += 1
            self.sensors.process_runtime_s += 1
            self.sensors.temperature_c += 0.35
            self.sensors.current_a = 1.25
            if self.remaining_ticks <= 0:
                completed = CompletedOperation(
                    machine_id=self.machine_id,
                    product_id=self.current_product_id or "",
                    process=self.current_process or "",
                )
                self.current_product_id = None
                self.current_process = None
                self.remaining_ticks = 0
                self.sensors.process_runtime_s = 0
                self.sensors.current_a = 0.7
                self.sensors.temperature_c = max(31.0, self.sensors.temperature_c - 1.5)
                self.cycle_count += 1
                self.machine.transition(MachineState.IDLE)
                return completed
        elif self.state in {MachineState.FAULT, MachineState.BLOCKED, MachineState.MAINTENANCE}:
            self.downtime_ticks += 1
        else:
            self.sensors.temperature_c = max(30.0, self.sensors.temperature_c - 0.1)
            self.sensors.current_a = 0.5
        return None

    def inject_fault(self, fault_type: FaultType, reason: str | None = None) -> None:
        self.induce_fault_symptom(fault_type)
        self.unavailable_reason = reason or fault_type.value
        if self.state != MachineState.FAULT:
            self.machine.transition(MachineState.FAULT)

    def induce_fault_symptom(self, fault_type: FaultType) -> None:
        if fault_type == FaultType.OVERHEAT:
            self.sensors.temperature_c = max(self.sensors.temperature_c, 95.0)
        elif fault_type == FaultType.JAM:
            self.sensors.jammed = True
            self.sensors.current_a = max(self.sensors.current_a, 3.4)
        elif fault_type == FaultType.SENSOR_FAILURE:
            self.sensors.sensor_ok = False
        elif fault_type == FaultType.CAMERA_FAILURE:
            self.sensors.camera_ok = False
        elif fault_type == FaultType.TIMEOUT:
            self.sensors.process_runtime_s = max(self.sensors.process_runtime_s, 99.0)
        elif fault_type == FaultType.COMMUNICATION_LOSS:
            self.sensors.heartbeat_age_s = max(self.sensors.heartbeat_age_s, 99.0)
        self.sensors.update_timestamp()

    def release_product_for_recovery(self) -> CompletedOperation | None:
        if self.current_product_id is None or self.current_process is None:
            return None
        operation = CompletedOperation(
            machine_id=self.machine_id,
            product_id=self.current_product_id,
            process=self.current_process,
        )
        self.current_product_id = None
        self.current_process = None
        self.remaining_ticks = 0
        self.sensors.process_runtime_s = 0
        return operation

    def recover(self) -> None:
        if self.state in {
            MachineState.FAULT,
            MachineState.MAINTENANCE,
            MachineState.EMERGENCY_STOP,
            MachineState.BLOCKED,
        }:
            if self.state == MachineState.BLOCKED:
                self.machine.transition(MachineState.FAULT)
            self.machine.transition(MachineState.RECOVERING)
            self.sensors.jammed = False
            self.sensors.sensor_ok = True
            self.sensors.camera_ok = True
            self.sensors.temperature_c = 35.0
            self.sensors.vibration_mm_s = 0.08
            self.sensors.current_a = 0.5
            self.sensors.heartbeat_age_s = 0
            self.sensors.process_runtime_s = 0
            self.unavailable_reason = None
            self.machine.transition(MachineState.IDLE)

    def emergency_stop(self) -> None:
        self.machine.emergency_stop()
        self.unavailable_reason = "Emergency stop"

    def status(self) -> MachineStatus:
        maintenance = self.health_scorer.recommend(
            SensorPoint(
                machine_id=self.machine_id,
                temperature_c=self.sensors.temperature_c,
                vibration_mm_s=self.sensors.vibration_mm_s,
                current_a=self.sensors.current_a,
                timestamp=self.sensors.timestamp,
            )
        )
        return MachineStatus(
            machine_id=self.machine_id,
            name=self.config.name,
            machine_type=self.config.machine_type,
            state=self.state,
            capabilities=list(self.config.capabilities),
            current_product_id=self.current_product_id,
            current_process=self.current_process,
            remaining_ticks=self.remaining_ticks,
            healthy=self.healthy,
            unavailable_reason=self.unavailable_reason,
            sensors=self.sensors,
            cycle_count=self.cycle_count,
            downtime_ticks=self.downtime_ticks,
            utilization_ticks=self.utilization_ticks,
            health_score=maintenance.health_score,
            maintenance_status=maintenance.status,
            maintenance_recommendation=maintenance.recommendation,
        )
