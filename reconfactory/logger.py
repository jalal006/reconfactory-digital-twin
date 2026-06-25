"""SQLite persistence for events, products, faults, and recovery actions."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import FactoryEvent, FaultRecord, MachineStatus, Product, RecoveryAction


class DataLogger:
    def __init__(self, db_path: str | Path = "data/factory.db", reset: bool = False) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if reset and self.db_path.exists():
            self.db_path.unlink()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    source TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS products (
                    product_id TEXT PRIMARY KEY,
                    product_type TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    quality TEXT NOT NULL,
                    current_location TEXT NOT NULL,
                    assigned_station TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    data_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS machines (
                    machine_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    machine_type TEXT NOT NULL,
                    state TEXT NOT NULL,
                    healthy INTEGER NOT NULL,
                    health_score REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    data_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS machine_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    machine_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    healthy INTEGER NOT NULL,
                    current_product_id TEXT,
                    data_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sensor_readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    machine_id TEXT NOT NULL,
                    temperature_c REAL NOT NULL,
                    vibration_mm_s REAL NOT NULL,
                    current_a REAL NOT NULL,
                    jammed INTEGER NOT NULL,
                    sensor_ok INTEGER NOT NULL,
                    camera_ok INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS faults (
                    fault_id TEXT PRIMARY KEY,
                    machine_id TEXT NOT NULL,
                    fault_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    likely_cause TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    detected_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS production_events (
                    event_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    product_id TEXT,
                    machine_id TEXT,
                    message TEXT NOT NULL,
                    data_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS recovery_actions (
                    action_id TEXT PRIMARY KEY,
                    fault_id TEXT NOT NULL,
                    machine_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    rerouted_products_json TEXT NOT NULL,
                    paused_products_json TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS maintenance_warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    machine_id TEXT NOT NULL,
                    health_score REAL NOT NULL,
                    status TEXT NOT NULL,
                    recommendation TEXT NOT NULL
                );
                """
            )

    def log_event(self, event: FactoryEvent) -> None:
        data = event.to_dict()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO events
                (event_id, timestamp, event_type, severity, source, message, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["event_id"],
                    data["timestamp"],
                    data["event_type"],
                    data["severity"],
                    data["source"],
                    data["message"],
                    json.dumps(data["data"], sort_keys=True),
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO production_events
                (event_id, timestamp, event_type, product_id, machine_id, message, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["event_id"],
                    data["timestamp"],
                    data["event_type"],
                    data["data"].get("product_id"),
                    data["data"].get("machine_id") or data["data"].get("station"),
                    data["message"],
                    json.dumps(data["data"], sort_keys=True),
                ),
            )

    def upsert_product(self, product: Product) -> None:
        data = product.to_dict()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO products
                (product_id, product_type, display_name, status, quality, current_location,
                 assigned_station, created_at, updated_at, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["product_id"],
                    data["product_type"],
                    data["display_name"],
                    data["status"],
                    data["quality"],
                    data["current_location"],
                    data["assigned_station"],
                    data["created_at"],
                    data["updated_at"],
                    json.dumps(data, sort_keys=True),
                ),
            )

    def log_machine_snapshot(self, status: MachineStatus) -> None:
        data = status.to_dict()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO machines
                (machine_id, name, machine_type, state, healthy, health_score,
                 updated_at, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["machine_id"],
                    data["name"],
                    data["machine_type"],
                    data["state"],
                    1 if data["healthy"] else 0,
                    data["health_score"],
                    data["sensors"]["timestamp"],
                    json.dumps(data, sort_keys=True),
                ),
            )
            conn.execute(
                """
                INSERT INTO machine_snapshots
                (timestamp, machine_id, state, healthy, current_product_id, data_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    data["sensors"]["timestamp"],
                    data["machine_id"],
                    data["state"],
                    1 if data["healthy"] else 0,
                    data["current_product_id"],
                    json.dumps(data, sort_keys=True),
                ),
            )
            conn.execute(
                """
                INSERT INTO sensor_readings
                (timestamp, machine_id, temperature_c, vibration_mm_s, current_a,
                 jammed, sensor_ok, camera_ok)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["sensors"]["timestamp"],
                    data["machine_id"],
                    data["sensors"]["temperature_c"],
                    data["sensors"]["vibration_mm_s"],
                    data["sensors"]["current_a"],
                    1 if data["sensors"]["jammed"] else 0,
                    1 if data["sensors"]["sensor_ok"] else 0,
                    1 if data["sensors"]["camera_ok"] else 0,
                ),
            )
            if data["maintenance_status"] in {"warning", "critical"}:
                conn.execute(
                    """
                    INSERT INTO maintenance_warnings
                    (timestamp, machine_id, health_score, status, recommendation)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        data["sensors"]["timestamp"],
                        data["machine_id"],
                        data["health_score"],
                        data["maintenance_status"],
                        data["maintenance_recommendation"],
                    ),
                )

    def log_fault(self, fault: FaultRecord) -> None:
        data = fault.to_dict()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO faults
                (fault_id, machine_id, fault_type, severity, likely_cause, recommendation,
                 explanation, detected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["fault_id"],
                    data["machine_id"],
                    data["fault_type"],
                    data["severity"],
                    data["likely_cause"],
                    data["recommendation"],
                    data["explanation"],
                    data["detected_at"],
                ),
            )

    def log_recovery_action(self, action: RecoveryAction) -> None:
        data = action.to_dict()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO recovery_actions
                (action_id, fault_id, machine_id, action_type, rerouted_products_json,
                 paused_products_json, explanation, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["action_id"],
                    data["fault_id"],
                    data["machine_id"],
                    data["action_type"],
                    json.dumps(data["rerouted_products"]),
                    json.dumps(data["paused_products"]),
                    data["explanation"],
                    data["created_at"],
                ),
            )

    def stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            product_counts = {
                row["status"]: row["count"]
                for row in conn.execute(
                    "SELECT status, COUNT(*) AS count FROM products GROUP BY status"
                )
            }
            fault_count = conn.execute("SELECT COUNT(*) AS count FROM faults").fetchone()[
                "count"
            ]
            event_count = conn.execute("SELECT COUNT(*) AS count FROM events").fetchone()[
                "count"
            ]
            rerouted_count = 0
            for row in conn.execute("SELECT rerouted_products_json FROM recovery_actions"):
                rerouted_count += len(json.loads(row["rerouted_products_json"]))
        return {
            "product_counts": product_counts,
            "fault_count": fault_count,
            "event_count": event_count,
            "rerouted_count": rerouted_count,
        }
