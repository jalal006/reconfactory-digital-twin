import sqlite3

import pytest

from reconfactory import FactorySupervisor
from reconfactory.logger import DataLogger


def test_sqlite_logger_records_products_events_and_faults(tmp_path):
    db_path = tmp_path / "factory.db"
    factory = FactorySupervisor(db_path=db_path, reset_database=True)
    factory.start()
    factory.create_product("red_block")
    factory.run_until_idle(max_ticks=40)

    stats = DataLogger(db_path).stats()

    assert stats["event_count"] > 0
    assert stats["product_counts"]["completed"] == 1


def test_station_batch_preserves_all_rows_with_one_commit(tmp_path, monkeypatch):
    factory = FactorySupervisor(enable_database=False)
    logger = DataLogger(tmp_path / "batch.db")
    statements = []
    connect = logger._connect

    def traced_connect():
        connection = connect()
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(logger, "_connect", traced_connect)
    logger.log_machine_snapshots(station.status() for station in factory.stations.values())
    assert sum(sql == "COMMIT" for sql in statements) == 1
    with sqlite3.connect(logger.db_path) as connection:
        for table in ("machines", "machine_snapshots", "sensor_readings"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == len(
                factory.stations
            )


def test_station_batch_failure_rolls_back_rows_and_warning_cache(tmp_path):
    factory = FactorySupervisor(enable_database=False)
    logger = DataLogger(tmp_path / "rollback.db")

    def interrupted_observation():
        yield next(iter(factory.stations.values())).status()
        raise RuntimeError("observation interrupted")

    with pytest.raises(RuntimeError, match="observation interrupted"):
        logger.log_machine_snapshots(interrupted_observation())
    assert logger._maintenance_states == {}
    with sqlite3.connect(logger.db_path) as connection:
        for table in ("machines", "machine_snapshots", "sensor_readings"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
