"""Send seeded degradation to a running demo; never starts a server or changes fault rules."""

import argparse
import json
import math
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
    parser.add_argument(
        "--hold-after",
        type=int,
        help="Stop degradation after this sample and hold that simulated reading",
    )
    parser.add_argument("--hold-seconds", type=float, default=120)
    args = parser.parse_args()
    if args.samples < 2:
        parser.error("--samples must be at least 2")
    if args.hold_after is not None and not 1 <= args.hold_after <= args.samples:
        parser.error("--hold-after must be between 1 and --samples")
    if not math.isfinite(args.hold_seconds) or args.hold_seconds < 0:
        parser.error("--hold-seconds must be finite and nonnegative")
    print(
        "Start production in the dashboard. Sending simulated telemetry; late degradation may trigger a real fault.",
        flush=True,
    )
    points = generate_sequence(
        args.machine, seed=args.seed, samples=args.samples, scenario=args.scenario
    )
    if args.hold_after is not None:
        points = points[: args.hold_after]

    def send(point):
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

    for point in points:
        send(point)
        time.sleep(0.75)
    if args.hold_after is not None:
        print(
            f"Holding simulated sample {args.hold_after} for {args.hold_seconds:g}s: "
            f"vibration={points[-1].vibration_mm_s:.3f} mm/s. "
            "Observe health-aware NEW assignments; existing missions stay assigned.",
            flush=True,
        )
        deadline = time.monotonic() + args.hold_seconds
        while time.monotonic() < deadline:
            send(points[-1])
            time.sleep(0.75)
    print("Telemetry scenario complete. Reset the demo to clear the simulated degradation.")


if __name__ == "__main__":
    main()
