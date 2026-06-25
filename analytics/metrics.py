"""Production metrics and experiment comparison helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reconfactory import FactorySupervisor
from reconfactory.models import FaultType


@dataclass(frozen=True)
class ExperimentResult:
    scenario: str
    products_completed: int
    products_rejected: int
    products_paused: int
    fault_count: int
    rerouted_products: int
    ticks: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "products_completed": self.products_completed,
            "products_rejected": self.products_rejected,
            "products_paused": self.products_paused,
            "fault_count": self.fault_count,
            "rerouted_products": self.rerouted_products,
            "ticks": self.ticks,
        }


def summarize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    stats = snapshot["stats"]
    return {
        "total_products": stats["total_products"],
        "completed_products": stats["completed_products"],
        "rejected_products": stats["rejected_products"],
        "paused_products": stats["paused_products"],
        "fault_count": stats["fault_count"],
        "rerouted_products": stats["rerouted_products"],
        "completion_rate": round(stats["completion_rate"], 3),
        "rejection_rate": round(stats["rejection_rate"], 3),
    }


def run_recovery_comparison(product_count: int = 12) -> dict[str, Any]:
    """Compare fail-stop behavior against ReConFactory rerouting behavior."""

    without_recovery = FactorySupervisor(enable_database=False)
    without_recovery.start()
    for _ in range(product_count):
        without_recovery.create_product("red_block")
    without_recovery.tick(2)
    without_recovery.stations["station_a"].inject_fault(
        FaultType.OVERHEAT, "fail-stop benchmark"
    )
    without_recovery.stop()
    no_recovery_snapshot = without_recovery.snapshot()

    with_recovery = FactorySupervisor(enable_database=False)
    with_recovery.start()
    for _ in range(product_count):
        with_recovery.create_product("red_block")
    with_recovery.tick(2)
    with_recovery.inject_fault("station_a", FaultType.OVERHEAT)
    with_recovery.run_until_idle(max_ticks=180)
    recovery_snapshot = with_recovery.snapshot()

    return {
        "without_recovery": ExperimentResult(
            scenario="fail_stop",
            products_completed=no_recovery_snapshot["stats"]["completed_products"],
            products_rejected=no_recovery_snapshot["stats"]["rejected_products"],
            products_paused=no_recovery_snapshot["stats"]["paused_products"],
            fault_count=1,
            rerouted_products=0,
            ticks=no_recovery_snapshot["tick"],
        ).to_dict(),
        "with_recovery": ExperimentResult(
            scenario="automatic_rerouting",
            products_completed=recovery_snapshot["stats"]["completed_products"],
            products_rejected=recovery_snapshot["stats"]["rejected_products"],
            products_paused=recovery_snapshot["stats"]["paused_products"],
            fault_count=recovery_snapshot["stats"]["fault_count"],
            rerouted_products=recovery_snapshot["stats"]["rerouted_products"],
            ticks=recovery_snapshot["tick"],
        ).to_dict(),
    }
