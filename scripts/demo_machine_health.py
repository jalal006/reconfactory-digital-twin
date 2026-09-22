"""Send seeded degradation to a running demo; never starts a server or changes fault rules."""

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maintenance.telemetry import SCENARIOS, generate_sequence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--machine", default="station_a")
    parser.add_argument("--scenario", choices=SCENARIOS, default="bearing")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--samples", type=int, default=90)
    args = parser.parse_args()
    print(
        "Start production in the dashboard. Sending simulated telemetry; late degradation may trigger a real fault.",
        flush=True,
    )
    for point in generate_sequence(
        args.machine, seed=args.seed, samples=args.samples, scenario=args.scenario
    ):
        payload = {
            "machine_id": point.machine_id,
            "temperature_c": point.temperature_c,
            "vibration_mm_s": point.vibration_mm_s,
            "current_a": point.current_a,
        }
        request = Request(
            args.url.rstrip("/") + "/api/telemetry",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            response.read()
        time.sleep(0.75)
    print("Telemetry scenario complete. Reset the demo to clear the simulated degradation.")


if __name__ == "__main__":
    main()
