"""Run recovery comparison experiment from the project plan."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analytics.metrics import run_recovery_comparison


def main() -> None:
    output = Path("data/generated_reports/recovery_comparison.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    result = run_recovery_comparison(product_count=12)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
