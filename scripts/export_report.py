"""Export CSV reports from the SQLite event log."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analytics.reports import export_event_report


def main() -> None:
    output = export_event_report()
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
