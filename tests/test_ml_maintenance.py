"""Deterministic ML and scheduling contracts, independent of ROS and Gazebo."""

import asyncio
import importlib.util
import json
import sqlite3
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from maintenance.features import FEATURE_NAMES, WINDOW_SIZE, extract_features, feature_rows
from maintenance.health import SensorPoint
from maintenance.ml import MLHealthEstimator, health_status, train_model
from maintenance.monitor import HealthMonitor
from maintenance.telemetry import generate_sequence
from reconfactory import FactorySupervisor
from reconfactory.models import FaultType


@pytest.fixture(scope="module")
def estimator():
    return train_model()


@pytest.fixture(scope="module")
def artifact(estimator, tmp_path_factory):
    path = tmp_path_factory.mktemp("health") / "model.joblib"
    estimator.save(path)
    return path


def test_feature_order_and_values():
    points = [SensorPoint("a", i, 2 * i, 3 * i) for i in range(12)]
    row = extract_features(points)
    assert FEATURE_NAMES[:3] == ("temperature_c_last", "vibration_mm_s_last", "current_a_last")
    assert len(FEATURE_NAMES) == len(row) == 12
    np.testing.assert_allclose(row[:3], [11, 22, 33])
    np.testing.assert_allclose(row[3:6], [5.5, 11, 16.5])
    np.testing.assert_allclose(row[6:9], np.std([[i, 2 * i, 3 * i] for i in range(12)], axis=0))
    np.testing.assert_allclose(row[9:], [1, 2, 3])


def test_rolling_window_and_warmup(estimator):
    points = generate_sequence(samples=30)
    np.testing.assert_allclose(extract_features(points), extract_features(points[-12:]))
    assert extract_features(points[:3]) is None
    assert extract_features([]) is None
    prediction = estimator.predict(points[:3])
    assert prediction.source == "rules"
    assert "warmup" in prediction.reasons[-1]


def test_invalid_features_do_not_poison_monitor():
    monitor = HealthMonitor()
    with pytest.raises(ValueError):
        monitor.observe(SensorPoint("a", float("nan"), 0.1, 1))
    assert not monitor.histories["a"]
    with pytest.raises(ValueError):
        extract_features([SensorPoint("a", 30, 0.1, 1), SensorPoint("b", 30, 0.1, 1)])


def test_seeded_sequences_and_training(estimator):
    assert generate_sequence(seed=5) == generate_sequence(seed=5)
    other = train_model()
    rows = feature_rows(generate_sequence(seed=900))
    np.testing.assert_allclose(estimator.scores(rows), other.scores(rows))


@pytest.mark.parametrize("scenario", ["bearing", "overheating", "mechanical_load"])
def test_degraded_scores_exceed_healthy(estimator, scenario):
    healthy = estimator.scores(feature_rows(generate_sequence(seed=20001)))
    degraded = estimator.scores(feature_rows(generate_sequence(seed=20001, scenario=scenario)))[
        -30:
    ]
    assert degraded.mean() > healthy.mean() + 0.1
    assert np.all((degraded >= 0) & (degraded <= 1))


def test_roundtrip_and_json(estimator, artifact):
    loaded = MLHealthEstimator.load(artifact)
    points = generate_sequence(scenario="bearing")
    assert loaded.predict(points) == estimator.predict(points)
    assert (
        json.loads(json.dumps(loaded.predict(points).to_dict()))["source"]
        == "ml_isolation_forest"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("feature_names", ["wrong"]),
        ("window_size", 2),
        ("schema_version", 999),
        ("sklearn_version", "0.0"),
        ("sha256", "invalid"),
    ],
)
def test_incompatible_metadata_fails(estimator, tmp_path, field, value):
    path = tmp_path / "model.joblib"
    estimator.save(path)
    metadata = json.loads(path.with_suffix(".json").read_text())
    metadata[field] = value
    path.with_suffix(".json").write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="unavailable/incompatible"):
        MLHealthEstimator.load(path)


def test_missing_model_and_rule_fallback(tmp_path):
    with pytest.raises(ValueError, match="train_health_model"):
        HealthMonitor("ml", tmp_path / "absent")
    assert (
        HealthMonitor("rules", tmp_path / "absent")
        .observe(SensorPoint("a", 35, 0.1, 0.8))
        .source
        == "rules"
    )
    with pytest.raises(ValueError, match="MAINTENANCE_MODE"):
        HealthMonitor("pretend")


def test_camera_and_rules_do_not_import_ml_dependencies():
    code = """
import sys
sys.modules['sklearn'] = None
sys.modules['joblib'] = None
from reconfactory import FactorySupervisor
from vision.opencv_inspector import OpenCVInspector
f = FactorySupervisor(enable_database=False, maintenance_mode='rules')
f.start()
f.tick()
assert f.stations['station_a'].health_prediction.source == 'rules'
"""
    subprocess.run([sys.executable, "-c", code], check=True, timeout=20)


@pytest.mark.parametrize(
    "score,status",
    [(0, "healthy"), (0.2, "watch"), (0.5, "degrading"), (0.8, "critical"), (1, "critical")],
)
def test_status_mapping(score, status):
    assert health_status(score) == status


def factory_with_risk(enabled=True):
    factory = FactorySupervisor(
        enable_database=False, maintenance_mode="rules", health_scheduling=enabled
    )
    factory.start()
    factory._update_machine_health()
    station = factory.stations["station_a"]
    station.health_prediction = replace(
        station.health_prediction, health_score=0.38, anomaly_score=0.62, status="degrading"
    )
    return factory


def test_scheduler_prefers_healthy_and_emits_once():
    factory = factory_with_risk()
    product = factory.create_product("red_block")
    assert factory._assign_product_to_processing_station(product, "drill")
    assert product.assigned_station == "station_b"
    events = [e for e in factory.events if e.event_type == "predictive_reroute"]
    assert len(events) == 1
    assert events[0].data["avoided_machine"] == "station_a"
    assert events[0].data["selected_machine"] == "station_b"
    factory._record_predictive_assignment()
    assert factory.predictive_diversions == 1


def test_capability_fault_and_disable_constraints():
    factory = factory_with_risk()
    product = factory.create_product("green_component")
    assert factory.scheduler.select_station(product, "assemble").machine_id == "station_a"
    factory.stations["station_b"].inject_fault(FaultType.OVERHEAT)
    assert factory.scheduler.select_station(product, "drill").machine_id == "station_a"
    factory = factory_with_risk(False)
    assert factory.scheduler.select_station(product, "drill").machine_id == "station_a"


def test_critical_exclusion_and_running_work_untouched():
    from reconfactory.models import MachineState

    factory = factory_with_risk()
    product = factory.create_product("green_component")
    station = factory.stations["station_a"]
    station.assign(product.product_id, "assemble")
    station.health_prediction = replace(station.health_prediction, status="critical")
    assert factory.scheduler.select_station(product, "assemble") is None
    assert station.current_product_id == product.product_id
    station.release_product_for_recovery()
    station.machine.transition(MachineState.IDLE)
    assert station.can_accept("assemble")
    assert factory.scheduler.select_station(product, "assemble") is None
    factory.scheduler.health_policy["critical_exclusion"] = False
    assert factory.scheduler.select_station(product, "assemble") == station


def test_transition_events_and_sqlite(tmp_path):
    factory = FactorySupervisor(
        db_path=tmp_path / "factory.db", maintenance_mode="rules", health_scheduling=True
    )
    factory.start()
    factory.tick(20)
    transitions = [e for e in factory.events if e.event_type == "machine_health_changed"]
    assert len(transitions) == len(factory.stations)
    with sqlite3.connect(factory.logger.db_path) as conn:
        data = json.loads(
            conn.execute("SELECT data_json FROM machine_snapshots LIMIT 1").fetchone()[0]
        )
    assert data["machine_health"]["source"] == "rules"


def test_snapshot_reset_and_bounded_online_history(artifact):
    factory = FactorySupervisor(
        enable_database=False,
        maintenance_mode="ml",
        health_model_path=artifact,
        health_scheduling=True,
    )
    factory.start()
    factory.tick(15)
    assert len(factory.health_monitor.histories["station_a"]) == WINDOW_SIZE
    snapshot = json.loads(json.dumps(factory.snapshot()))
    assert snapshot["machines"][0]["machine_health"]["source"] == "ml_isolation_forest"
    factory.reset()
    assert factory.maintenance_mode == "ml"
    assert factory.scheduler.health_policy["enabled"]
    assert not factory.health_monitor.histories


def test_api_health_and_telemetry_validation(monkeypatch):
    import reconfactory

    factory = factory_with_risk()
    monkeypatch.setattr(reconfactory, "FactorySupervisor", lambda **_: factory)
    spec = importlib.util.spec_from_file_location(
        "health_api_test", Path(__file__).resolve().parents[1] / "app/main.py"
    )
    backend = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, backend)
    spec.loader.exec_module(backend)
    result = asyncio.run(backend.maintenance_state())
    assert result["mode"] == "rules"
    assert result["scheduling_enabled"]
    payload = backend.TelemetryRequest(
        machine_id="station_a", temperature_c=40, vibration_mm_s=1, current_a=1
    )
    assert asyncio.run(backend.telemetry(payload)) == {"ok": True}
    assert factory.stations["station_a"].sensors.temperature_c == 40
    with pytest.raises(ValueError):
        backend.TelemetryRequest(
            machine_id="station_a", temperature_c=float("nan"), vibration_mm_s=1, current_a=1
        )


def test_paired_experiment_uses_same_workload(artifact):
    from analytics.maintenance_experiment import run_health_comparison

    result = run_health_comparison(ticks=60, model_path=artifact)
    assert result["baseline"]["products_created"] == result["health_aware"]["products_created"]
    assert result["baseline"]["predictive_diversions"] == 0
    assert result["baseline"]["hard_faults"] == result["health_aware"]["hard_faults"]


def test_amr_health_choice_still_waits_for_delivery():
    from reconfactory.models import ProductStatus

    factory = FactorySupervisor(
        enable_database=False,
        maintenance_mode="rules",
        health_scheduling=True,
        transport_mode="amr",
    )
    factory.start()
    factory._update_machine_health()
    a = factory.stations["station_a"]
    a.health_prediction = replace(
        a.health_prediction, status="degrading", health_score=0.38, anomaly_score=0.62
    )
    product = factory.create_product("red_block")
    factory.tracker.move(product.product_id, "vision")
    product.completed_processes.append("visual_inspection")
    product.status = ProductStatus.QUEUED
    factory.transport.heartbeat(True)
    factory.transport.dispatch()
    assert factory.transport.active.destination == "station_b"
    assert product.current_location == "vision"
    assert factory.stations["station_b"].current_product_id is None
    assert factory.predictive_diversions == 1


def test_maintenance_warning_is_written_only_on_transition(tmp_path):
    factory = FactorySupervisor(db_path=tmp_path / "factory.db", maintenance_mode="rules")
    station = factory.stations["station_a"]
    station.sensors.temperature_c = 90
    station.sensors.vibration_mm_s = 4
    station.sensors.current_a = 3
    for _ in range(10):
        factory.logger.log_machine_snapshot(station.status())
    with sqlite3.connect(factory.logger.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM maintenance_warnings").fetchone()[0] == 1


def test_predictive_event_survives_database_and_csv(tmp_path):
    import csv

    from analytics.reports import export_event_report

    factory = FactorySupervisor(
        db_path=tmp_path / "factory.db", maintenance_mode="rules", health_scheduling=True
    )
    factory.start()
    factory._update_machine_health()
    a = factory.stations["station_a"]
    a.health_prediction = replace(
        a.health_prediction, status="degrading", health_score=0.38, anomaly_score=0.62
    )
    product = factory.create_product("red_block")
    factory._assign_product_to_processing_station(product, "drill")
    path = export_event_report(factory.logger.db_path, tmp_path / "events.csv")
    with path.open(newline="", encoding="utf-8") as file:
        row = next(r for r in csv.DictReader(file) if r["event_type"] == "predictive_reroute")
    assert json.loads(row["data_json"])["selected_machine"] == "station_b"
