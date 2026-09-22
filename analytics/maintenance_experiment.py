"""Paired scheduling trial with identical exogenous telemetry and workload."""

from pathlib import Path

from maintenance.ml import DEFAULT_MODEL, MLHealthEstimator
from maintenance.telemetry import generate_sequence
from reconfactory import FactorySupervisor


def run_health_comparison(
    *, seed: int = 42, ticks: int = 180, model_path: str | Path = DEFAULT_MODEL
) -> dict:
    if ticks < 40:
        raise ValueError("Experiment needs at least 40 ticks")
    # Same time-indexed degradation in each arm, independent of allocation. This
    # deliberately cannot claim health scheduling prevents an exogenous fault.
    telemetry = {
        machine: generate_sequence(
            machine,
            seed=seed + i,
            samples=ticks,
            scenario="bearing" if machine == "station_a" else "healthy",
        )
        for i, machine in enumerate(("station_a", "station_b"))
    }
    results = {}
    for enabled in (False, True):
        factory = FactorySupervisor(
            enable_database=False,
            transport_mode="simulated",
            vision_source="synthetic",
            maintenance_mode="ml",
            health_model_path=model_path,
            health_scheduling=enabled,
        )
        factory.start()
        assignments = {"station_a": 0, "station_b": 0}
        assigned_risk = []
        seen = set()
        for tick in range(ticks):
            if tick >= 12 and tick < ticks - 30 and tick % 6 == 0:
                factory.create_product("red_block")
            for machine, sequence in telemetry.items():
                p = sequence[tick]
                factory.apply_telemetry(machine, p.temperature_c, p.vibration_mm_s, p.current_a)
            factory.tick()
            for event in factory.events:
                if event.event_id in seen:
                    continue
                seen.add(event.event_id)
                if event.event_type == "product_assigned":
                    machine = event.data.get("station")
                    if machine in assignments:
                        assignments[machine] += 1
                        assigned_risk.append(
                            factory.stations[machine].health_prediction.anomaly_score
                        )
        state = factory.snapshot()
        stats = state["stats"]
        results["health_aware" if enabled else "baseline"] = {
            "products_created": stats["total_products"],
            "products_completed": stats["completed_products"],
            "unfinished_products": stats["total_products"]
            - stats["completed_products"]
            - stats["rejected_products"],
            "throughput_per_tick": stats["throughput_per_tick"],
            "average_cycle_time_ticks": stats["average_cycle_time_ticks"],
            "downtime_ticks": stats["total_downtime_ticks"],
            "hard_faults": stats["fault_count"],
            "reactive_reroutes": stats["rerouted_products"],
            "predictive_diversions": stats["predictive_diversions"],
            "assignments": assignments,
            "mean_assignment_anomaly": sum(assigned_risk) / max(1, len(assigned_risk)),
            "machine_utilization": {
                k: s.utilization_ticks / ticks for k, s in factory.stations.items()
            },
        }
    return {
        "model_metadata": MLHealthEstimator.load(model_path).metadata,
        "seed": seed,
        "ticks": ticks,
        "workload": "red_block every 6 ticks after warmup, 30 tick drain",
        "scenario": "Identical progressive bearing degradation on A; identical healthy B; no repair in either arm",
        "limitations": "Exogenous degradation: cannot demonstrate prevented faults. Tick simulation, not wall-time or AMR performance.",
        **results,
    }
