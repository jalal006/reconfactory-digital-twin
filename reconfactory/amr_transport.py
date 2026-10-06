"""Delivery gating owned by FactorySupervisor; no ROS imports."""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .energy import distance, leg_energy
from .models import Product, ProductStatus, Severity
from .transport import TERMINAL, TransportRequest, load_station_goals, task_timeout_s

if TYPE_CHECKING:
    from .supervisor import FactorySupervisor


class FactoryTransport:
    def __init__(self, supervisor: FactorySupervisor, station_file: Path) -> None:
        self.factory = supervisor
        self.stations = load_station_goals(station_file)
        self.active: TransportRequest | None = None
        self.last_heartbeat = 0.0
        self.ready = False
        self.request_time = 0.0
        self.delivery_timeout_s = task_timeout_s() + 60.0
        self.final_results: dict[str, tuple[bool, str | None]] = {}
        self.robot_pose: dict[str, float] | None = None
        self.cancel_time = 0.0
        self.cancelled_time = 0.0
        self.retired: dict[str, dict] = {}
        self.motion_session = None
        self.motion_sequence = -1
        self.motion_totals = (0.0, 0.0, 0.0)
        self.retired_motion_sessions: set[str] = set()

    def heartbeat(
        self, ready: bool, pose: dict | None = None, motion: dict | None = None
    ) -> None:
        self.last_heartbeat = time.monotonic()
        self.ready = ready
        self.robot_pose = pose
        if motion is not None:
            self._motion_update(motion)

    def _motion_update(self, motion):
        totals = tuple(motion[k] for k in ("elapsed_s", "distance_m", "rotation_rad"))
        if any(not math.isfinite(value) or value < 0 for value in totals):
            raise ValueError("Motion counters must be finite and nonnegative")
        if motion["session_id"] in self.retired_motion_sessions:
            return
        if motion["session_id"] != self.motion_session:
            baseline = (0.0, 0.0, 0.0) if self.motion_session is None else totals
            if self.motion_session is not None:
                self.retired_motion_sessions.add(self.motion_session)
            self.motion_session = motion["session_id"]
            self.motion_sequence = -1
            self.motion_totals = baseline
        if motion["sequence"] <= self.motion_sequence:
            return
        delta = tuple(a - b for a, b in zip(totals, self.motion_totals, strict=True))
        if any(value < 0 for value in delta):
            raise ValueError("Motion counters cannot decrease within a session")
        if delta[0] == 0 and (delta[1] or delta[2]):
            raise ValueError("Motion requires positive elapsed time")
        self.motion_sequence, self.motion_totals = motion["sequence"], totals
        dt, meters, radians = delta
        if dt <= 0:
            return
        e = self.factory.energy
        task = self.active
        at_dock = bool(
            self.robot_pose
            and distance(self.robot_pose, self.stations["charging_dock"])
            <= e.battery.config.dock_tolerance_m
        )
        e.update(
            dt,
            meters / dt,
            radians / dt,
            loaded=bool(task and task.payload_loaded),
            at_charger=bool(
                task
                and task.mission_type == "charge"
                and task.status == "delivered"
                and at_dock
                and meters / dt < 0.03
                and radians / dt < 0.05
                and self.factory.running
            ),
        )
        if (
            task
            and task.status not in TERMINAL
            and task.payload_loaded
            and self.robot_pose
            and e.battery.remaining_wh
            < e.battery.config.capacity_wh * e.battery.config.critical_soc
            + leg_energy(
                e.battery.config,
                distance(self.robot_pose, self.stations[task.destination]),
                True,
            )
        ):
            e.critical(
                "Remaining loaded delivery estimate violates critical reserve; payload held"
            )
        if e.state == "critical_energy":
            self.cancel()
        if (
            task
            and task.mission_type == "charge"
            and task.status == "delivered"
            and e.state == "ready"
        ):
            self.active = None

    def _charge(self):
        e = self.factory.energy
        current = self.robot_pose or self.stations["home"]
        if not e.begin_charge_trip(current):
            return
        self.active = TransportRequest(
            "AMR",
            "home",
            "charging_dock",
            mission_type="charge",
            phase="delivery",
            estimated_energy_wh=leg_energy(
                e.battery.config, distance(current, self.stations["charging_dock"]), False
            ),
            energy_start_wh=e.battery.energy_consumed_wh,
        )
        self.request_time = time.monotonic()
        self._event("charging_mission_requested", self.active)

    def snapshot(self) -> dict[str, Any]:
        return {
            "ready": self.ready and time.monotonic() - self.last_heartbeat < 5.0,
            "active_task": self.active.to_dict() if self.active else None,
            "robot_pose": self.robot_pose,
            "energy": self.factory.energy.snapshot(),
        }

    def cancel(self) -> None:
        if self.active and self.active.status not in TERMINAL:
            self.active.cancel_requested = True

    def invalidate_destination(self, machine_id: str, fault_id: str | None = None) -> None:
        task = self.active
        if (
            not task
            or task.destination != machine_id
            or task.status in TERMINAL
            or task.cancel_requested
        ):
            return
        task.replan_reason = "destination_unavailable"
        task.original_destination = task.destination
        task.fault_id = fault_id
        task.replan_state = "cancelling"
        self.cancel_time = time.monotonic()
        self.cancel()
        self._event("transport_replan_requested", task)

    def _replan(self) -> None:
        old = self.active
        if not old or old.status != "cancelled" or old.replan_state != "awaiting_replan":
            return
        if not self.snapshot()["ready"]:
            return
        f = self.factory
        product = f.tracker.get(old.product_id)
        process = product.next_process()
        previous = f.stations[old.destination]
        occupied = {
            p.current_location
            for p in f.tracker.all()
            if p.product_id != product.product_id
            and p.status not in {ProductStatus.COMPLETED, ProductStatus.REJECTED}
        }
        station = f.scheduler.select_station(
            product, process, previous.config.machine_type, excluded=occupied
        )
        if station is None or (station.machine_id == "vision" and f.pending_vision_product_id):
            return
        if not f.energy.authorize(
            product.product_id,
            old.origin,
            station.machine_id,
            self.robot_pose or self.stations[old.origin],
            old.payload_loaded,
        ):
            old.failure_reason = f.energy.reason or "Replacement waiting for energy"
            # Never overwrite the held fault mission with an independent charger goal.
            if not old.payload_loaded and f.energy.state == "charge_required":
                self.retired[old.task_id] = old.to_dict()
                product.status = ProductStatus.QUEUED
                self._charge()
            return
        new = TransportRequest(
            product.product_id,
            old.origin,
            station.machine_id,
            phase="delivery" if old.payload_loaded else "pickup",
            payload_loaded=old.payload_loaded,
            supersedes_task_id=old.task_id,
            original_destination=old.destination,
            replan_reason=old.replan_reason,
            fault_id=old.fault_id,
            cancel_latency_s=old.cancel_latency_s,
            replan_latency_s=time.monotonic() - self.cancelled_time,
            estimated_energy_wh=f.energy.estimate_wh,
            energy_start_wh=f.energy.battery.energy_consumed_wh,
        )
        self.retired[old.task_id] = old.to_dict()
        # Bound replay bookkeeping; older messages still fail closed by task identity.
        if len(self.retired) > 256:
            self.retired.pop(next(iter(self.retired)))
        self.active = new
        self.request_time = time.monotonic()
        product.status = ProductStatus.IN_TRANSIT
        f._persist_product(product)
        f.rerouted_product_count += 1
        self._event("transport_replanned", new)
        f._record_predictive_assignment()

    def check_timeout(self) -> None:
        if time.monotonic() - self.last_heartbeat > 2:
            self.factory.energy.battery.is_charging = False
        if self.active and self.active.status not in TERMINAL:
            station = self.factory.stations.get(self.active.destination)
            if station and not station.healthy:
                self.invalidate_destination(station.machine_id)
            e = self.factory.energy
            if e.state == "critical_energy":
                self.cancel()
        if self.active and self.active.status not in TERMINAL:
            now = time.monotonic()
            if (
                now - self.last_heartbeat > 10.0
                or now - self.request_time > self.delivery_timeout_s
            ):
                self.receive(
                    {
                        **self.active.to_dict(),
                        "status": "failed",
                        "failure_reason": "AMR heartbeat or delivery timeout",
                    }
                )

    def finish_quality(self, product: Product, accepted: bool, reason: str | None) -> None:
        self.final_results[product.product_id] = (accepted, reason)
        product.status = ProductStatus.QUEUED
        product.assigned_station = None
        self.factory._persist_product(product)

    def dispatch(self) -> None:
        f = self.factory
        if not f.running or not f._line_can_move():
            return
        if self.active:
            self._replan()
            return
        # Unavailable transport never falls back to an instant delivery.
        if not self.snapshot()["ready"]:
            return
        candidates = [
            p
            for p in f.tracker.all()
            if p.status in {ProductStatus.WAITING, ProductStatus.QUEUED}
        ]
        # Clear occupied stations before collecting another input product.
        candidates.sort(key=lambda p: p.current_location == "input_queue")
        for product in candidates:
            outcome = self.final_results.get(product.product_id)
            process = product.next_process()
            if outcome is not None:
                destination = "accepted_output" if outcome[0] else "reject_output"
            else:
                machine_type = (
                    "inspection"
                    if process == "visual_inspection"
                    else "quality"
                    if process == "quality_check"
                    else "processing"
                )
                occupied = {
                    p.current_location
                    for p in f.tracker.all()
                    if p.product_id != product.product_id
                    and p.status not in {ProductStatus.COMPLETED, ProductStatus.REJECTED}
                }
                station = f.scheduler.select_station(
                    product, process, machine_type, excluded=occupied
                )
                if station is None:
                    continue
                destination = station.machine_id
                if destination == "vision" and f.pending_vision_product_id:
                    continue
            if destination == product.current_location:
                self._dequeue(product.product_id)
                self._arrive(product, destination)
                continue
            request = TransportRequest(
                product.product_id, product.current_location, destination
            )
            if not f.energy.authorize(
                product.product_id,
                product.current_location,
                destination,
                self.robot_pose or self.stations["home"],
            ):
                if f.energy.state == "charge_required":
                    self._charge()
                return
            request.estimated_energy_wh = f.energy.estimate_wh
            request.energy_start_wh = f.energy.battery.energy_consumed_wh
            TransportRequest.from_dict(request.to_dict(), self.stations)
            self.active = request
            origin_station = f.stations.get(product.current_location)
            if (
                origin_station
                and not origin_station.healthy
                and origin_station.config.machine_type == "processing"
            ):
                f.rerouted_product_count += 1
                self._event("transport_rerouted", request)
            self._dequeue(product.product_id)
            self.request_time = time.monotonic()
            product.status = ProductStatus.IN_TRANSIT
            product.assigned_station = None
            f._persist_product(product)
            self._event("transport_requested", request)
            if outcome is None:
                f._record_predictive_assignment()
            return

    def _dequeue(self, product_id: str) -> None:
        for queue in (
            self.factory.input_queue,
            self.factory.processing_queue,
            self.factory.quality_queue,
        ):
            while product_id in queue:
                queue.remove(product_id)

    def _event(self, kind: str, request: TransportRequest) -> None:
        self.factory._emit(
            kind,
            f"{request.product_id}: {request.origin} -> {request.destination}: {request.status}"
            + (f" ({request.failure_reason})" if request.failure_reason else ""),
            source="amr_01",
            severity=Severity.WARNING
            if request.status in {"failed", "cancelled"}
            else Severity.INFO,
            data={**request.to_dict(), "robot_pose": self.robot_pose},
        )

    def receive(self, payload: dict) -> None:
        retired = self.retired.get(payload.get("task_id"))
        if retired and all(
            payload.get(k) == retired[k] for k in ("product_id", "destination", "status")
        ):
            return
        task = self.active
        if task is None or payload.get("task_id") != task.task_id:
            raise ValueError("No matching active transport task")
        destination = self.factory.stations.get(task.destination)
        if payload.get("status") == "delivered" and destination and not destination.healthy:
            self.invalidate_destination(task.destination)
        if not task.update(payload):
            return
        if task.status in TERMINAL:
            task.actual_energy_wh = (
                self.factory.energy.battery.energy_consumed_wh - task.energy_start_wh
            )
        self._event(f"transport_{task.status}", task)
        if task.mission_type == "charge":
            e = self.factory.energy
            if task.status == "delivered":
                if (
                    not self.robot_pose
                    or distance(self.robot_pose, self.stations["charging_dock"])
                    > e.battery.config.dock_tolerance_m
                ):
                    e.state, e.reason = (
                        "blocked_energy",
                        "Charger arrival lacks a matching localized dock pose",
                    )
                    e.event("charge_failed")
                else:
                    e.arrived_at_charger()
            elif task.status in {"failed", "cancelled"}:
                e.state, e.reason = (
                    "blocked_energy",
                    "Charging navigation failed or cancelled; inspect robot before reset",
                )
                e.event("charge_failed")
            return
        product = self.factory.tracker.get(task.product_id)
        if task.status == "delivered":
            self._arrive(product, task.destination)
            self.active = None
        elif task.status == "cancelled" and task.replan_state == "cancelling":
            self.cancelled_time = time.monotonic()
            task.cancel_latency_s = self.cancelled_time - self.cancel_time
            task.replan_state = "awaiting_replan"
            task.failure_reason = (
                "Destination unavailable; waiting for compatible station and AMR readiness"
            )
            product.status = ProductStatus.IN_TRANSIT
            self.factory._persist_product(product)
            self._event("transport_goal_cancelled", task)
        elif task.status in {"failed", "cancelled"}:
            if task.replan_state or task.supersedes_task_id:
                task.replan_state = "blocked_transport"
                self._event("transport_replan_failed", task)
            self.factory._pause_product(
                product,
                task.failure_reason
                or f"AMR transport {task.status}; inspect payload before reset",
            )

    def _arrive(self, product: Product, destination: str) -> None:
        f = self.factory
        outcome = self.final_results.pop(product.product_id, None)
        if outcome is not None:
            f.tracker.mark_quality(product.product_id, accepted=outcome[0], reason=outcome[1])
            f.product_tick_history[product.product_id]["completed_tick"] = f.tick_count
            f._emit(
                "product_completed" if outcome[0] else "product_rejected",
                f"{product.product_id} delivered to {destination}.",
                source="quality",
                data={
                    "product_id": product.product_id,
                    "accepted": outcome[0],
                    "defect_reason": outcome[1],
                },
            )
        else:
            if product.current_location != destination:
                f.tracker.move(product.product_id, destination)
            station = f.stations[destination]
            process = product.next_process()
            if f.running and station.can_accept(process):
                station.assign(product.product_id, process)
                product.assigned_station = destination
                product.status = ProductStatus.PROCESSING
                f._emit(
                    "product_assigned",
                    f"{product.product_id} delivered to {station.config.name} for {process}.",
                    source="scheduler",
                    data={
                        "product_id": product.product_id,
                        "station": destination,
                        "process": process,
                    },
                )
            else:
                product.status = ProductStatus.QUEUED
        product.mark_updated()
        f._persist_product(product)
