"""Deterministic supervisor experiment; logical navigation, not a Nav2 benchmark."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reconfactory import FactorySupervisor  # noqa: E402
from reconfactory.energy import Battery, BatteryConfig, distance  # noqa: E402
from reconfactory.models import ProductStatus  # noqa: E402


def run(aware: bool, products: int = 10, max_seconds: int = 3000) -> dict:
    f = FactorySupervisor(
        enable_database=False,
        transport_mode="amr",
        vision_source="synthetic",
        maintenance_mode="rules",
    )
    f.energy.battery = Battery(BatteryConfig(initial_soc=0.21))
    if not aware:
        # The baseline skips admission estimates, not depletion or critical-stop physics.
        f.energy.authorize = lambda *args, **kwargs: True
    for _ in range(products):
        f.create_product("red_block")
    f.start()
    pose = dict(f.transport.stations["home"])
    meters = 0.0
    moving_seconds = 0
    completed_seconds = None
    for second in range(1, max_seconds + 1):
        task = f.transport.active
        moved = 0.0
        if task and task.status not in {"delivered", "failed", "cancelled"}:
            if task.cancel_requested:
                f.transport.receive({**task.to_dict(), "status": "cancelled"})
            else:
                if task.status == "requested":
                    f.transport.receive({**task.to_dict(), "status": "accepted"})
                    f.transport.receive({**task.to_dict(), "status": "navigating"})
                target = f.transport.stations[
                    task.origin if task.phase == "pickup" else task.destination
                ]
                remaining = distance(pose, target)
                moved = min(0.35, remaining)
                if remaining:
                    fraction = moved / remaining
                    pose = {
                        "x": pose["x"] + fraction * (target["x"] - pose["x"]),
                        "y": pose["y"] + fraction * (target["y"] - pose["y"]),
                        "yaw": 0.0,
                    }
        meters += moved
        moving_seconds += bool(moved)
        f.transport.heartbeat(
            True,
            pose,
            dict(
                session_id="experiment",
                sequence=second,
                elapsed_s=second,
                distance_m=meters,
                rotation_rad=0.0,
            ),
        )
        if task and task.status == "navigating" and not task.cancel_requested:
            target = f.transport.stations[
                task.origin if task.phase == "pickup" else task.destination
            ]
            if distance(pose, target) < 1e-9:
                f.transport.receive(
                    {
                        **task.to_dict(),
                        "status": "navigating" if task.phase == "pickup" else "delivered",
                        "phase": "delivery",
                    }
                )
        # Match the configured 0.65 s production clock without double-counting battery time.
        for _ in range(math.floor(second / 0.65) - math.floor((second - 1) / 0.65)):
            f.tick()
        if all(p.status == ProductStatus.COMPLETED for p in f.tracker.all()):
            completed_seconds = second
            break
        if f.energy.state in {"critical_energy", "blocked_energy"}:
            break
    completed = sum(p.status == ProductStatus.COMPLETED for p in f.tracker.all())
    missions = [e.data for e in f.events if e.event_type == "transport_delivered"]
    errors = [
        m["estimated_energy_wh"] - m["actual_energy_wh"]
        for m in missions
        if m.get("estimated_energy_wh") is not None
    ]
    return {
        "products_created": products,
        "products_completed": completed,
        "unfinished_products": products - completed,
        "completion_time_s": completed_seconds,
        "observed_time_s": second,
        "distance_m": meters,
        "moving_fraction": moving_seconds / second,
        "energy": f.energy.snapshot(),
        "successful_missions": len(missions),
        "mean_estimate_minus_actual_wh": sum(errors) / len(errors) if errors else None,
        "critical_stops": sum(e.event_type == "critical_energy" for e in f.events),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "data/generated_reports/energy_comparison.json"
    )
    args = parser.parse_args()
    result = {
        "model": "Deterministic Wh model; initial SOC 0.21, 100 Wh, speed 0.35 m/s",
        "workload": "10 red blocks queued at time zero; same stations and product logic",
        "limitations": "Straight-line logical travel; no Nav2, obstacles or angular motion. Charging accelerated. Not physical battery validation or a speedup claim.",
        "baseline": run(False),
        "energy_aware": run(True),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
