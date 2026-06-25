"""Report helpers for saved ReConFactory data."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path


def export_event_report(
    db_path: str | Path = "data/factory.db",
    output_path: str | Path = "data/generated_reports/events.csv",
) -> Path:
    db = Path(db_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn, output.open("w", newline="", encoding="utf-8") as file:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT timestamp, event_type, severity, source, message FROM events ORDER BY timestamp"
        ).fetchall()
        writer = csv.DictWriter(
            file, fieldnames=["timestamp", "event_type", "severity", "source", "message"]
        )
        writer.writeheader()
        writer.writerows(dict(row) for row in rows)
    return output
