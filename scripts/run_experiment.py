"""Run recovery comparison experiment from the project plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analytics.metrics import run_recovery_comparison


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maintenance", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ticks", type=int, default=180)
    args = parser.parse_args()
    output = Path(
        "data/generated_reports/maintenance_comparison.json"
        if args.maintenance
        else "data/generated_reports/recovery_comparison.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.maintenance:
        from analytics.maintenance_experiment import run_health_comparison

        result = run_health_comparison(seed=args.seed, ticks=args.ticks)
    else:
        result = run_recovery_comparison(product_count=12)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
