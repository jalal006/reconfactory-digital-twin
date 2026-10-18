"""Sequential isolated live trials; record failures as well as successful measurements."""

import argparse
import json
import signal
import subprocess
import sys
import time
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]


def summarize(trials):
    rows = [
        t["measurement"]
        for t in trials
        if t.get("measurement")
        and t.get("exit_code") == 0
        and t["measurement"].get("scenario") == "manager-crash"
    ]
    return (
        {
            name: {
                "median_s": median([r[name] for r in rows]),
                "worst_s": max(r[name] for r in rows),
            }
            for name in ("command_inhibition_s", "physical_stop_s")
        }
        if rows
        else {}
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manager-trials", type=int, default=3)
    args = parser.parse_args()
    if args.manager_trials < 1:
        parser.error("At least one manager trial is required")
    directory = ROOT / "logs" / f"safety_campaign_{time.time_ns()}"
    directory.mkdir(parents=True)
    scenarios = [["--safety", "manager-crash"] for _ in range(args.manager_trials)] + [
        ["--safety", "backend-outage"],
        ["--safety", "gate-crash"],
        ["--fault-replan"],
        ["--energy"],
        ["--resilience", "manager-restart", "--unsafe-baseline"],
    ]
    report = {
        "trials": [],
        "historical_stop_range_s": [4.29, 5.87],
        "limits": "Individual simulation observations, not certified or guaranteed stopping bounds. Baseline intentionally restores old ungated smoother output in isolated domain 73 only.",
    }
    for index, flags in enumerate(scenarios):
        print(f"Trial {index + 1}/{len(scenarios)}: {' '.join(flags)}", flush=True)
        existing = set((ROOT / "logs/amr_smoke").glob("safety_*.json"))
        with (directory / f"trial_{index + 1}.log").open("w") as log:
            try:
                process = subprocess.Popen(
                    [sys.executable, "scripts/run_amr_smoke.py", *flags],
                    cwd=ROOT,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                code = process.wait(timeout=1200)
            except subprocess.TimeoutExpired:
                # Let the smoke runner execute its owned-stack cleanup before continuing.
                process.send_signal(signal.SIGINT)
                process.wait(timeout=60)
                code = 124
        trial = {"flags": flags, "exit_code": code}
        new = set((ROOT / "logs/amr_smoke").glob("safety_*.json")) - existing
        if new:
            trial["measurement"] = json.loads(
                max(new, key=lambda p: p.stat().st_mtime).read_text()
            )
        elif "--unsafe-baseline" in flags:
            p = ROOT / "logs/amr_smoke/manager-restart.json"
            if code == 0 and p.exists():
                trial["measurement"] = json.loads(p.read_text())
        report["trials"].append(trial)
        report["independent_manager_loss"] = summarize(report["trials"])
        (directory / "results.json").write_text(json.dumps(report, indent=2))
        print(f"Trial exit {code}; report {directory / 'results.json'}", flush=True)
    if any(t["exit_code"] for t in report["trials"]):
        raise SystemExit("Some trials failed; inspect recorded logs, do not infer success")


if __name__ == "__main__":
    main()
