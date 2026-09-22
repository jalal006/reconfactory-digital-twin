"""Generate synthetic sensor data for later analytics work."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maintenance.health import HealthScorer
from maintenance.telemetry import SCENARIOS, generate_sequence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    output = Path("data/sample_sensor_data.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "tick",
                "machine_id",
                "temperature_c",
                "vibration_mm_s",
                "current_a",
                "health_score",
                "scenario",
            ],
        )
        writer.writeheader()
        for scenario in SCENARIOS:
            for index, machine_id in enumerate(["station_a", "station_b", "quality"]):
                for tick, point in enumerate(
                    generate_sequence(
                        machine_id, seed=args.seed + index, samples=400, scenario=scenario
                    )
                ):
                    writer.writerow(
                        {
                            "tick": tick,
                            "machine_id": machine_id,
                            "temperature_c": point.temperature_c,
                            "vibration_mm_s": point.vibration_mm_s,
                            "current_a": point.current_a,
                            "health_score": HealthScorer().score(point),
                            "scenario": scenario,
                        }
                    )
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
