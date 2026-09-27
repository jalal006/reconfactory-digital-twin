"""Run the paired fault-in-transit logical experiment from the repository root."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.replanning_experiment import run_replanning_comparison  # noqa: E402


def main():
    result = run_replanning_comparison()
    output = Path("data/generated_reports/replanning_comparison.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
