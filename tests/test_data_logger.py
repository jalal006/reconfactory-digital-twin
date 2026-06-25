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
