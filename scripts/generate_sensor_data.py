"""Generate synthetic sensor data for later analytics work."""

from __future__ import annotations

import csv
from pathlib import Path


def main() -> None:
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
            ],
        )
        writer.writeheader()
        for tick in range(1, 401):
            for machine_id in ["station_a", "station_b", "quality"]:
                degradation = tick / 400
                writer.writerow(
                    {
                        "tick": tick,
                        "machine_id": machine_id,
                        "temperature_c": round(34 + degradation * 18, 2),
                        "vibration_mm_s": round(0.08 + degradation * 2.4, 3),
                        "current_a": round(0.8 + degradation * 0.9, 2),
                        "health_score": round(max(0, 1 - degradation * 0.65), 3),
                    }
                )
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
