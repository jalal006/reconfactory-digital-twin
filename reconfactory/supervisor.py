"""Top-level factory supervisor."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from vision.inspector import VisionInspector

from .config import (
    load_fault_rules,
    load_machine_configs,
    load_product_recipes,
    load_routing_weights,
)
from .faults import DiagnosisEngine, FaultDetector
from .logger import DataLogger
from .models import (
    FactoryEvent,
    FaultRecord,
    FaultType,
    MachineState,
    Product,
    ProductStatus,
    RecoveryAction,
    Severity,
)
from .reconfiguration import ReconfigurationManager
from .scheduler import ProductionScheduler
from .stations import CompletedOperation, StationController
from .tracker import ProductTracker

VISUAL_SYNC = {
    "min_transition_ms": 650,
    "max_transition_ms": 950,
    "browser_px_per_second": 420,
    "gazebo_min_transition_ms": 650,
    "gazebo_max_transition_ms": 950,
    "gazebo_meters_per_second": 4.5,
    "gazebo_robot_meters_per_second": 4.5,
    "gazebo_catchup_multiplier": 1.55,
    "gazebo_latency_multiplier": 0.0,
}

AUTO_TICK_SECONDS = VISUAL_SYNC["min_transition_ms"] / 1000.0


class FactorySupervisor:
    """Coordinates the simulated production line."""

    def __init__(
        self,
        config_dir: str | Path = "config",
        *,
        enable_database: bool = True,
        db_path: str | Path = "data/factory.db",
        reset_database: bool = False,
    ) -> None:
        self.config_dir = Path(config_dir)
        self.recipes = load_product_recipes(self.config_dir)
        self.machine_configs = load_machine_configs(self.config_dir)
        self.fault_rules = load_fault_rules(self.config_dir)
        self.routing_weights = load_routing_weights(self.config_dir)

        self.tracker = ProductTracker(self.recipes)
        self.stations = {
            machine_id: StationController(config)
            for machine_id, config in self.machine_configs.items()
        }
        self.scheduler = ProductionScheduler(self.stations, self.routing_weights)
        self.fault_detector = FaultDetector(self.fault_rules)
        self.diagnosis_engine = DiagnosisEngine()
        self.reconfiguration_manager = ReconfigurationManager()
        self.vision_inspector = VisionInspector(self.recipes)
        self.logger = DataLogger(db_path, reset=reset_database) if enable_database else None

        self.input_queue: deque[str] = deque()
        self.processing_queue: deque[str] = deque()
        self.quality_queue: deque[str] = deque()
        self.events: deque[FactoryEvent] = deque(maxlen=300)
        self.faults: list[FaultRecord] = []
        self.recovery_actions: list[RecoveryAction] = []
        self.running = False
        self.tick_count = 0
        self.simulation_speed = 1.0
        self.rerouted_product_count = 0
        self.product_tick_history: dict[str, dict[str, int | None]] = {}
        self.gazebo_visuals: dict[str, Any] = {
            "source": "browser",
            "products": {},
            "product_locations": {},
            "processing_locations": [],
            "done_locations": [],
            "active_routes": [],
            "active_route_locations": [],
            "updated_at": None,
        }
        self.last_decision = "Factory initialized. Start production to begin."

        self._emit(
            "factory_initialized",
            "Factory supervisor initialized with default digital twin layout.",
            source="supervisor",
        )

    def start(self) -> dict[str, Any]:
        for station in self.stations.values():
            station.start()
        self.running = True
        self.last_decision = "Production started."
        self._emit("factory_started", "Production started.", source="supervisor")
        return self.snapshot()

    def stop(self) -> dict[str, Any]:
        self.running = False
        self.last_decision = "Production paused by operator."
        self._emit("factory_stopped", "Production paused by operator.", source="supervisor")
        return self.snapshot()

    def reset(self, *, clear_database: bool = False) -> dict[str, Any]:
        db_path = self.logger.db_path if self.logger else "data/factory.db"
        enable_database = self.logger is not None
        self.__init__(
            self.config_dir,
            enable_database=enable_database,
            db_path=db_path,
            reset_database=clear_database,
        )
        return self.snapshot()

    def emergency_stop(self) -> dict[str, Any]:
        self.running = False
        for station in self.stations.values():
            station.emergency_stop()
        self.last_decision = "Emergency stop engaged. All stations are unavailable."
        self._emit(
            "emergency_stop",
            self.last_decision,
            severity=Severity.CRITICAL,
            source="supervisor",
        )
        return self.snapshot()

    def create_product(
        self, product_type: str, defect_flags: Iterable[str] | None = None
    ) -> Product:
        product = self.tracker.create_product(product_type, defect_flags)
        self.product_tick_history[product.product_id] = {
            "created_tick": self.tick_count,
            "completed_tick": None,
        }
        self.input_queue.append(product.product_id)
        self._persist_product(product)
        self._emit(
            "product_created",
            f"{product.display_name} {product.product_id} entered the input queue.",
            source="input_station",
            data={"product_id": product.product_id, "product_type": product_type},
        )
        return product

    def tick(self, steps: int = 1) -> dict[str, Any]:
        for _ in range(max(1, steps)):
            if not self.running:
                break
            self.tick_count += 1
            self._detect_faults()
            self._tick_stations()
            self._detect_faults()
            if self._line_can_move():
                self._assign_work()
            self._persist_machine_snapshots()
        return self.snapshot()

    def run_until_idle(self, max_ticks: int = 200) -> dict[str, Any]:
        for _ in range(max_ticks):
            self.tick()
            if self.is_idle():
                break
        return self.snapshot()

    def is_idle(self) -> bool:
        active_station = any(
            station.state == MachineState.RUNNING for station in self.stations.values()
        )
        return (
            self.running
            and not self.input_queue
            and not self.processing_queue
            and not self.quality_queue
            and not active_station
        )

    def inject_fault(
        self, machine_id: str, fault_type: FaultType | str, *, reason: str | None = None
    ) -> dict[str, Any]:
        fault = FaultType(fault_type)
        station = self._station(machine_id)
        fault_count_before = len(self.faults)
        station.induce_fault_symptom(fault)
        self._emit(
            "fault_symptom_injected",
            f"Operator injected {fault.value} symptoms on {station.config.name}.",
            severity=Severity.WARNING,
            source=machine_id,
            data={"machine_id": machine_id, "fault_type": fault.value},
        )
        self._detect_faults()
        if len(self.faults) == fault_count_before:
            self._handle_fault(machine_id, fault, reason or f"Manual {fault.value} injection")
        return self.snapshot()

    def set_speed(self, speed: float) -> dict[str, Any]:
        self.simulation_speed = max(0.25, min(4.0, float(speed)))
        self._emit(
            "simulation_speed_changed",
            f"Simulation speed set to {self.simulation_speed:.2f}x.",
            source="dashboard",
            data={"speed": self.simulation_speed},
        )
        return self.snapshot()

    def update_gazebo_visuals(self, visuals: dict[str, Any]) -> dict[str, Any]:
        products = visuals.get("products", {})
        if not isinstance(products, dict):
            products = {}
        live_products = {product.product_id for product in self.tracker.all()}
        sanitized: dict[str, dict[str, float]] = {}
        product_locations = visuals.get("product_locations", {})
        if not isinstance(product_locations, dict):
            product_locations = {}
        for product_id, pose in products.items():
            if product_id not in live_products or not isinstance(pose, dict):
                continue
            try:
                sanitized[product_id] = {
                    "x": float(pose.get("x", 0.0)),
                    "y": float(pose.get("y", 0.0)),
                    "z": float(pose.get("z", 0.0)),
                    "yaw": float(pose.get("yaw", 0.0)),
                }
            except (TypeError, ValueError):
                continue
        self.gazebo_visuals = {
            "source": "gazebo",
            "products": sanitized,
            "product_locations": {
                str(product_id): str(location)
                for product_id, location in product_locations.items()
                if product_id in live_products and isinstance(location, str)
            },
            "processing_locations": [
                str(location)
                for location in visuals.get("processing_locations", [])
                if isinstance(location, str)
            ],
            "done_locations": [
                str(location)
                for location in visuals.get("done_locations", [])
                if isinstance(location, str)
            ],
            "active_routes": [
                str(route)
                for route in visuals.get("active_routes", [])
                if isinstance(route, str)
            ],
            "active_route_locations": [
                str(location)
                for location in visuals.get("active_route_locations", [])
                if isinstance(location, str)
            ],
            "updated_at": visuals.get("updated_at"),
        }
        return {"accepted": len(sanitized)}

    def recover_machine(self, machine_id: str) -> dict[str, Any]:
        station = self._station(machine_id)
        station.recover()
        self._emit(
            "machine_recovered",
            f"{station.config.name} returned to idle service.",
            source=machine_id,
            data={"machine_id": machine_id},
        )
        self.last_decision = f"{station.config.name} recovered and returned to scheduling."
        if self.running and self._line_can_move():
            self._resume_paused_products()
            self._assign_work()
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        products = [product.to_dict() for product in self.tracker.all()]
        active_faults = self._active_faults_by_machine()
        queue_lengths = self._machine_queue_lengths()
        machines = []
        for station in self.stations.values():
            machine = station.status().to_dict()
            machine["queue_length"] = queue_lengths.get(station.machine_id, 0)
            machine["active_fault"] = active_faults.get(station.machine_id)
            machines.append(machine)
        stats = self._stats(products, machines)
        return {
            "running": self.running,
            "tick": self.tick_count,
            "simulation_speed": self.simulation_speed,
            "last_decision": self.last_decision,
            "queues": {
                "input": list(self.input_queue),
                "processing": list(self.processing_queue),
                "quality": list(self.quality_queue),
            },
            "products": products,
            "machines": machines,
            "faults": [fault.to_dict() for fault in self.faults[-20:]],
            "recovery_actions": [action.to_dict() for action in self.recovery_actions[-20:]],
            "events": [event.to_dict() for event in list(self.events)[-80:]],
            "stats": stats,
            "recipes": {
                product_type: recipe.to_dict() for product_type, recipe in self.recipes.items()
            },
            "route_status": self._route_status(),
            "visual_sync": dict(VISUAL_SYNC),
            "gazebo_visuals": self.gazebo_visuals,
        }

    def _tick_stations(self) -> None:
        completed: list[CompletedOperation] = []
        for station in self.stations.values():
            operation = station.tick()
            if operation:
                completed.append(operation)
        for operation in completed:
            self._handle_completed_operation(operation)

    def _handle_completed_operation(self, operation: CompletedOperation) -> None:
        station = self._station(operation.machine_id)
        product = self.tracker.get(operation.product_id)
        self.tracker.complete_process(product.product_id, operation.process)
        self.tracker.assign_station(product.product_id, None)

        if operation.machine_id == "vision":
            result = self.vision_inspector.inspect(product)
            product.inspection_confidence = result.confidence
            if not result.passed:
                rejected = self.tracker.mark_quality(
                    product.product_id,
                    accepted=False,
                    reason=result.defect_reason or "Vision inspection failed",
                )
                self._persist_product(rejected)
                self._emit(
                    "product_rejected",
                    f"{product.product_id} rejected by vision: {rejected.defect_reason}.",
                    severity=Severity.WARNING,
                    source="vision",
                    data={"product_id": product.product_id, "inspection": result.to_dict()},
                )
                return
            self.tracker.queue(product.product_id, "processing_buffer")
            self.processing_queue.append(product.product_id)
            self._emit(
                "vision_passed",
                f"{product.product_id} identified as {product.display_name} with {result.confidence:.0%} confidence.",
                source="vision",
                data={"product_id": product.product_id, "inspection": result.to_dict()},
            )
        elif operation.machine_id == "quality":
            accepted = "quality_defect" not in product.defect_flags
            finalized = self.tracker.mark_quality(
                product.product_id,
                accepted=accepted,
                reason=None if accepted else "Final quality check failed",
            )
            history = self.product_tick_history.setdefault(
                product.product_id,
                {"created_tick": self.tick_count, "completed_tick": None},
            )
            history["completed_tick"] = self.tick_count
            event_type = "product_completed" if accepted else "product_rejected"
            severity = Severity.INFO if accepted else Severity.WARNING
            self._emit(
                event_type,
                f"{product.product_id} sent to {finalized.current_location}.",
                severity=severity,
                source="quality",
                data={"product_id": product.product_id, "accepted": accepted},
            )
        else:
            next_process = product.next_process()
            if next_process == "quality_check":
                self.tracker.queue(product.product_id, "quality_buffer")
                self.quality_queue.append(product.product_id)
            elif next_process:
                self.tracker.queue(product.product_id, "processing_buffer")
                self.processing_queue.append(product.product_id)
            self._emit(
                "process_completed",
                f"{station.config.name} completed {operation.process} for {product.product_id}.",
                source=operation.machine_id,
                data={"product_id": product.product_id, "process": operation.process},
            )
        self._persist_product(product)

    def _assign_work(self) -> None:
        self._assign_input_to_vision()
        self._assign_processing_queue()
        self._assign_quality_queue()

    def _assign_input_to_vision(self) -> None:
        if not self.input_queue:
            return
        vision = self.stations.get("vision")
        if not vision or not vision.can_accept("visual_inspection"):
            return
        product_id = self.input_queue.popleft()
        product = self.tracker.move(product_id, "vision")
        product.status = ProductStatus.PROCESSING
        product.assigned_station = "vision"
        product.mark_updated()
        vision.assign(product_id, "visual_inspection")
        self._persist_product(product)
        self._emit(
            "product_assigned",
            f"{product_id} moved to vision inspection.",
            source="scheduler",
            data={"product_id": product_id, "station": "vision"},
        )

    def _assign_processing_queue(self) -> None:
        retained: deque[str] = deque()
        while self.processing_queue:
            product_id = self.processing_queue.popleft()
            product = self.tracker.get(product_id)
            if product.status in {ProductStatus.COMPLETED, ProductStatus.REJECTED}:
                continue
            if product.status == ProductStatus.PAUSED:
                retained.append(product_id)
                continue
            process = product.next_process()
            if process is None:
                continue
            if process == "quality_check":
                self.quality_queue.append(product_id)
                continue
            assigned = self._assign_product_to_processing_station(product, process)
            if not assigned and product.status != ProductStatus.PAUSED:
                retained.append(product_id)
        self.processing_queue = retained

    def _assign_quality_queue(self) -> None:
        retained: deque[str] = deque()
        quality = self.stations.get("quality")
        while self.quality_queue:
            product_id = self.quality_queue.popleft()
            product = self.tracker.get(product_id)
            if product.status in {ProductStatus.COMPLETED, ProductStatus.REJECTED}:
                continue
            if product.status == ProductStatus.PAUSED:
                retained.append(product_id)
                continue
            if not quality or not quality.can_accept("quality_check"):
                if quality and not quality.healthy:
                    self._pause_product(product, "Quality station is unavailable.")
                else:
                    retained.append(product_id)
                continue
            product = self.tracker.move(product_id, "quality")
            product.status = ProductStatus.PROCESSING
            product.assigned_station = "quality"
            product.mark_updated()
            quality.assign(product_id, "quality_check")
            self._persist_product(product)
            self._emit(
                "product_assigned",
                f"{product_id} moved to quality control.",
                source="scheduler",
                data={"product_id": product_id, "station": "quality"},
            )
        self.quality_queue = retained

    def _assign_product_to_processing_station(
        self,
        product: Product,
        process: str,
        *,
        action: RecoveryAction | None = None,
    ) -> bool:
        station = self.scheduler.select_station(product, process, "processing")
        if station:
            previous_station = product.assigned_station
            product = self.tracker.move(product.product_id, station.machine_id)
            product.status = ProductStatus.PROCESSING
            product.assigned_station = station.machine_id
            product.mark_updated()
            station.assign(product.product_id, process)
            self._persist_product(product)
            if action and previous_station != station.machine_id:
                action.rerouted_products.append(product.product_id)
                self.rerouted_product_count += 1
            self.last_decision = (
                f"{product.product_id} assigned to {station.config.name} for {process}."
            )
            self._emit(
                "product_assigned",
                self.last_decision,
                source="scheduler",
                data={
                    "product_id": product.product_id,
                    "process": process,
                    "station": station.machine_id,
                },
            )
            return True

        compatible = self.scheduler.compatible_stations(process, "processing")
        healthy_supported = self.scheduler.healthy_supported(process, "processing")
        if compatible and not healthy_supported:
            self._pause_product(
                product,
                f"No healthy processing station can perform {process}.",
                action=action,
            )
        elif not compatible:
            self._pause_product(
                product,
                f"No configured processing station supports {process}.",
                action=action,
            )
        return False

    def _detect_faults(self) -> None:
        for detected in self.fault_detector.evaluate(self.stations):
            self._handle_fault(
                detected.machine_id,
                detected.fault_type,
                detected.message,
                manual=False,
            )

    def _handle_fault(
        self,
        machine_id: str,
        fault_type: FaultType,
        reason: str,
        *,
        manual: bool = True,
    ) -> None:
        station = self._station(machine_id)
        if station.state == MachineState.FAULT:
            return
        station.inject_fault(fault_type, reason)
        fault = self.diagnosis_engine.diagnose(station, fault_type)
        self.faults.append(fault)
        if self.logger:
            self.logger.log_fault(fault)
        trigger = "Manual" if manual else "Automatic"
        self.last_decision = (
            f"{trigger} fault detected on {station.config.name}: {fault.explanation}"
        )
        self._emit(
            "fault_detected",
            self.last_decision,
            severity=fault.severity,
            source=machine_id,
            data=fault.to_dict(),
        )
        action = self._reconfigure_after_fault(station, fault)
        self.recovery_actions.append(action)
        if self.logger:
            self.logger.log_recovery_action(action)
        self._emit(
            "reconfiguration_completed",
            action.explanation,
            severity=Severity.WARNING,
            source="reconfiguration_manager",
            data=action.to_dict(),
        )

    def _reconfigure_after_fault(
        self, station: StationController, fault: FaultRecord
    ) -> RecoveryAction:
        action = self.reconfiguration_manager.create_action(fault.fault_id, station.machine_id)
        released = station.release_product_for_recovery()
        if released:
            product = self.tracker.get(released.product_id)
            product.assigned_station = station.machine_id
            self.tracker.move(product.product_id, "recovery_buffer")
            product.status = ProductStatus.QUEUED
            product.recovery_notes.append(
                f"Released from {station.config.name} after {fault.fault_type.value}."
            )
            product.mark_updated()
            if station.config.machine_type == "processing":
                assigned = self._assign_product_to_processing_station(
                    product,
                    released.process,
                    action=action,
                )
                if not assigned and product.status != ProductStatus.PAUSED:
                    self.processing_queue.appendleft(product.product_id)
            else:
                self._pause_product(
                    product,
                    f"{station.config.name} failed during {released.process}; no alternate station is configured.",
                    action=action,
                )

        if station.config.machine_type == "processing":
            self._reassess_processing_queue(action)
        elif station.config.machine_type == "conveyor":
            self.running = False
            action.explanation = "Conveyor fault stopped line movement. Products remain in safe buffers until recovery."
        return action

    def _reassess_processing_queue(self, action: RecoveryAction) -> None:
        retained: deque[str] = deque()
        while self.processing_queue:
            product_id = self.processing_queue.popleft()
            product = self.tracker.get(product_id)
            if product.status == ProductStatus.PAUSED:
                retained.append(product_id)
                continue
            process = product.next_process()
            if not process or process == "quality_check":
                retained.append(product_id)
                continue
            if self.scheduler.healthy_supported(process, "processing"):
                retained.append(product_id)
            else:
                self._pause_product(
                    product,
                    f"No healthy station remains for required process {process}.",
                    action=action,
                )
        self.processing_queue = retained

    def _resume_paused_products(self) -> None:
        for product in self.tracker.by_status(ProductStatus.PAUSED):
            process = product.next_process()
            if not process:
                continue
            if process == "quality_check":
                if self.scheduler.healthy_supported(process, "quality"):
                    self.tracker.queue(product.product_id, "quality_buffer")
                    self.quality_queue.append(product.product_id)
            elif self.scheduler.healthy_supported(process, "processing"):
                self.tracker.queue(product.product_id, "processing_buffer")
                self.processing_queue.append(product.product_id)

    def _pause_product(
        self,
        product: Product,
        reason: str,
        *,
        action: RecoveryAction | None = None,
    ) -> None:
        paused = self.tracker.pause(product.product_id, reason)
        if action and paused.product_id not in action.paused_products:
            action.paused_products.append(paused.product_id)
        self._persist_product(paused)
        self._emit(
            "product_paused",
            f"{paused.product_id} paused safely: {reason}",
            severity=Severity.WARNING,
            source="reconfiguration_manager",
            data={"product_id": paused.product_id, "reason": reason},
        )

    def _line_can_move(self) -> bool:
        conveyor = self.stations.get("conveyor_main")
        return conveyor is None or conveyor.healthy

    def _station(self, machine_id: str) -> StationController:
        try:
            return self.stations[machine_id]
        except KeyError as exc:
            raise KeyError(f"Unknown machine id: {machine_id}") from exc

    def _emit(
        self,
        event_type: str,
        message: str,
        *,
        source: str,
        severity: Severity = Severity.INFO,
        data: dict[str, Any] | None = None,
    ) -> FactoryEvent:
        event = FactoryEvent(
            event_type=event_type,
            message=message,
            severity=severity,
            source=source,
            data=data or {},
        )
        self.events.append(event)
        if self.logger:
            self.logger.log_event(event)
        return event

    def _persist_product(self, product: Product) -> None:
        if self.logger:
            self.logger.upsert_product(product)

    def _persist_machine_snapshots(self) -> None:
        if not self.logger:
            return
        for station in self.stations.values():
            self.logger.log_machine_snapshot(station.status())

    def _stats(
        self, products: list[dict[str, Any]], machines: list[dict[str, Any]]
    ) -> dict[str, Any]:
        total = len(products)
        completed = sum(1 for product in products if product["status"] == "completed")
        rejected = sum(1 for product in products if product["status"] == "rejected")
        paused = sum(1 for product in products if product["status"] == "paused")
        active = sum(
            1
            for product in products
            if product["status"] in {"waiting", "queued", "processing", "in_transit"}
        )
        utilization = {
            machine["machine_id"]: (
                machine["utilization_ticks"]
                / max(1, machine["utilization_ticks"] + machine["downtime_ticks"])
            )
            for machine in machines
        }
        cycle_times = []
        for history in self.product_tick_history.values():
            if history.get("completed_tick") is not None:
                cycle_times.append(
                    int(history["completed_tick"]) - int(history.get("created_tick") or 0)
                )
        total_downtime = sum(machine["downtime_ticks"] for machine in machines)
        recovery_action_count = len(self.recovery_actions)
        successful_recoveries = sum(
            1
            for action in self.recovery_actions
            if action.rerouted_products or action.paused_products or action.action_type
        )
        health = {
            machine["machine_id"]: {
                "score": machine["health_score"],
                "status": machine["maintenance_status"],
                "recommendation": machine["maintenance_recommendation"],
            }
            for machine in machines
        }
        return {
            "total_products": total,
            "completed_products": completed,
            "rejected_products": rejected,
            "paused_products": paused,
            "active_products": active,
            "fault_count": len(self.faults),
            "rerouted_products": self.rerouted_product_count,
            "completion_rate": completed / total if total else 0.0,
            "rejection_rate": rejected / total if total else 0.0,
            "machine_utilization": utilization,
            "machine_health": health,
            "throughput_per_tick": completed / max(1, self.tick_count),
            "average_cycle_time_ticks": (
                sum(cycle_times) / len(cycle_times) if cycle_times else 0.0
            ),
            "total_downtime_ticks": total_downtime,
            "recovery_success_rate": (
                successful_recoveries / recovery_action_count if recovery_action_count else 1.0
            ),
            "average_recovery_time_ticks": 1.0 if recovery_action_count else 0.0,
        }

    def _machine_queue_lengths(self) -> dict[str, int]:
        lengths = {machine_id: 0 for machine_id in self.stations}
        lengths["vision"] = len(self.input_queue)
        lengths["quality"] = len(self.quality_queue)
        for product_id in self.processing_queue:
            product = self.tracker.get(product_id)
            process = product.next_process()
            if not process:
                continue
            for station in self.scheduler.compatible_stations(process, "processing"):
                lengths[station.machine_id] = lengths.get(station.machine_id, 0) + 1
        return lengths

    def _active_faults_by_machine(self) -> dict[str, dict[str, Any]]:
        active: dict[str, dict[str, Any]] = {}
        for fault in self.faults:
            station = self.stations.get(fault.machine_id)
            if station and station.state == MachineState.FAULT:
                active[fault.machine_id] = fault.to_dict()
        return active

    def _route_status(self) -> dict[str, str]:
        station_a = self.stations["station_a"]
        station_b = self.stations["station_b"]
        conveyor = self.stations["conveyor_main"]
        quality = self.stations["quality"]
        vision = self.stations["vision"]
        status = {
            "input_to_vision": "blocked"
            if not vision.healthy or not conveyor.healthy
            else "active",
            "vision_to_buffer": "blocked"
            if not vision.healthy or not conveyor.healthy
            else "active",
            "vision_to_station_a": "blocked" if not station_a.healthy else "active",
            "vision_to_station_b": "blocked" if not station_b.healthy else "active",
            "processing_buffer_to_station_a": "blocked" if not station_a.healthy else "active",
            "processing_buffer_to_station_b": "blocked" if not station_b.healthy else "active",
            "station_a_to_quality_buffer": (
                "blocked" if not station_a.healthy or not quality.healthy else "active"
            ),
            "station_a_to_quality": (
                "blocked" if not station_a.healthy or not quality.healthy else "active"
            ),
            "station_b_to_quality_buffer": (
                "blocked" if not station_b.healthy or not quality.healthy else "active"
            ),
            "station_b_to_quality": (
                "blocked" if not station_b.healthy or not quality.healthy else "active"
            ),
            "quality_buffer_to_quality": "blocked" if not quality.healthy else "active",
            "quality_to_accepted": "blocked" if not quality.healthy else "active",
            "quality_to_reject": "blocked" if not quality.healthy else "active",
        }
        return status
