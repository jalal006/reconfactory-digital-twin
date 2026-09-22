"""Delivery gating owned by FactorySupervisor; no ROS imports."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

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

    def heartbeat(self, ready: bool, pose: dict | None = None) -> None:
        self.last_heartbeat = time.monotonic()
        self.ready = ready
        self.robot_pose = pose

    def snapshot(self) -> dict[str, Any]:
        return {
            "ready": self.ready and time.monotonic() - self.last_heartbeat < 5.0,
            "active_task": self.active.to_dict() if self.active else None,
            "robot_pose": self.robot_pose,
        }

    def cancel(self) -> None:
        if self.active and self.active.status not in TERMINAL:
            self.active.cancel_requested = True

    def check_timeout(self) -> None:
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
        if self.active or not f.running or not f._line_can_move():
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
            data=request.to_dict(),
        )

    def receive(self, payload: dict) -> None:
        task = self.active
        if task is None or payload.get("task_id") != task.task_id:
            raise ValueError("No matching active transport task")
        if not task.update(payload):
            return
        self._event(f"transport_{task.status}", task)
        product = self.factory.tracker.get(task.product_id)
        if task.status == "delivered":
            self._arrive(product, task.destination)
            self.active = None
        elif task.status in {"failed", "cancelled"}:
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
