from analytics.metrics import run_recovery_comparison, summarize_snapshot
from reconfactory import FactorySupervisor


def test_snapshot_summary_contains_core_metrics():
    factory = FactorySupervisor(enable_database=False)
    factory.start()
    factory.create_product("red_block")
    snapshot = factory.run_until_idle(max_ticks=40)

    summary = summarize_snapshot(snapshot)

    assert summary["total_products"] == 1
    assert summary["completed_products"] == 1
    assert summary["completion_rate"] == 1.0


def test_recovery_comparison_reports_both_scenarios():
    result = run_recovery_comparison(product_count=3)

    assert result["without_recovery"]["scenario"] == "fail_stop"
    assert result["with_recovery"]["scenario"] == "automatic_rerouting"
    assert result["with_recovery"]["fault_count"] == 1
