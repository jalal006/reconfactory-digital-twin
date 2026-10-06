"""Battery and supervisor charging contracts, without ROS or Gazebo."""

import json
import math
import sqlite3
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_amr_replanning import acknowledge, fault, transit
from test_amr_transport import STATIONS, MockClient, NavigationRunner

from reconfactory import FactorySupervisor
from reconfactory.energy import Battery, BatteryConfig, battery_ros_fields, estimate_mission
from reconfactory.logger import DataLogger
from reconfactory.models import ProductStatus
from reconfactory.transport import TransportRequest


def factory(soc=0.21, mode="amr"):
    f = FactorySupervisor(
        enable_database=False,
        transport_mode=mode,
        vision_source="synthetic",
        maintenance_mode="rules",
    )
    f.energy.battery = Battery(replace(f.energy.battery.config, initial_soc=soc))
    f.start()
    return f


def motion(seq, elapsed, meters=0, radians=0, session="test"):
    return dict(
        session_id=session,
        sequence=seq,
        elapsed_s=elapsed,
        distance_m=meters,
        rotation_rad=radians,
    )


def charging_factory():
    f = factory()
    p = f.create_product("red_block")
    f.transport.heartbeat(True, STATIONS["home"])
    f.transport.dispatch()
    t = f.transport.active
    assert t.mission_type == "charge"
    f.transport.heartbeat(True, STATIONS["charging_dock"])
    for status in ("accepted", "navigating", "delivered"):
        f.transport.receive({**t.to_dict(), "status": status})
    return f, p, t


def test_energy_equation_and_payload():
    c = BatteryConfig()
    empty, loaded = Battery(c), Battery(c)
    expected = 18 * 10 / 3600 + 10 * (0.2 * 0.4 + 0.03 * 0.2)
    assert empty.update(10, 0.4, 0.2) == pytest.approx(expected)
    assert loaded.update(10, 0.4, 0.2, payload_loaded=True) > expected
    idle = Battery(c)
    assert idle.update(10) < expected


def test_energy_partition_invariance_and_reverse_motion():
    a, b = Battery(BatteryConfig()), Battery(BatteryConfig())
    a.update(10, -0.4, -0.2)
    for _ in range(100):
        b.update(0.1, 0.4, 0.2)
    assert a.remaining_wh == pytest.approx(b.remaining_wh)


@pytest.mark.parametrize(
    "dt,v,w", [(-1, 0, 0), (math.inf, 0, 0), (1, math.nan, 0), (1, 0, math.inf)]
)
def test_invalid_updates_do_not_mutate(dt, v, w):
    b = Battery(BatteryConfig())
    before = b.snapshot()
    with pytest.raises(ValueError):
        b.update(dt, v, w)
    assert b.snapshot() == before


@pytest.mark.parametrize(
    "kw",
    [
        {"capacity_wh": 0},
        {"initial_soc": 2},
        {"critical_soc": 0.3},
        {"charging_power_w": 1},
        {"linear_cost_wh_per_m": -1},
        {"payload_multiplier": 0.5},
    ],
)
def test_invalid_config(kw):
    with pytest.raises(ValueError):
        BatteryConfig(**kw)


def test_empty_clamp_zero_dt_and_gradual_target():
    b = Battery(BatteryConfig(initial_soc=0.1))
    b.update(1e8, 1)
    assert b.remaining_wh == 0
    assert b.update(0) == 0
    b.update(1, charging=True)
    assert 0 < b.state_of_charge < 0.8
    b.update(1000, charging=True)
    assert b.state_of_charge == pytest.approx(0.8)
    assert not b.is_charging
    assert b.energy_charged_wh > 0


def test_estimate_distance_and_loaded_pickup_omission():
    c = BatteryConfig()
    short = estimate_mission(c, STATIONS["home"], STATIONS["input_queue"], STATIONS["vision"])
    long = estimate_mission(
        c, STATIONS["home"], STATIONS["input_queue"], STATIONS["accepted_output"]
    )
    loaded = estimate_mission(
        c, STATIONS["input_queue"], STATIONS["home"], STATIONS["vision"], payload_loaded=True
    )
    assert 0 < loaded < short < long


def test_short_mission_allowed_long_mission_deferred():
    f = factory(0.23)
    assert f.energy.authorize("P", "input_queue", "vision", STATIONS["home"])
    assert not f.energy.authorize("P", "input_queue", "accepted_output", STATIONS["home"])
    assert f.energy.state == "charge_required"


def test_low_soc_defers_without_product_arrival():
    f, p, t = charging_factory()
    assert p.current_location == "input_queue"
    assert p.status != ProductStatus.IN_TRANSIT
    assert not t.payload_loaded
    assert f.energy.state == "charging"
    assert f.energy.deferred["product_id"] == p.product_id


def test_charging_is_gradual_then_production_resumes():
    f, p, _ = charging_factory()
    before = f.energy.battery.remaining_wh
    f.transport.heartbeat(True, STATIONS["charging_dock"], motion(1, 1))
    assert before < f.energy.battery.remaining_wh < 80
    assert f.transport.active.mission_type == "charge"
    f.transport.heartbeat(True, STATIONS["charging_dock"], motion(2, 40))
    assert f.energy.state == "ready" and f.transport.active is None
    f.transport.dispatch()
    assert f.transport.active.product_id == p.product_id
    assert f.transport.active.destination == "vision"
    assert f.energy.deferred is None


@pytest.mark.parametrize("condition", ["away", "moving", "stopped"])
def test_charging_requires_dock_stationary_and_running(condition):
    f, _, _ = charging_factory()
    before = f.energy.battery.remaining_wh
    if condition == "stopped":
        f.stop()
    pose = STATIONS["home"] if condition == "away" else STATIONS["charging_dock"]
    f.transport.heartbeat(True, pose, motion(1, 1, 1 if condition == "moving" else 0))
    assert f.energy.battery.remaining_wh < before


def test_no_charge_before_successful_navigation_or_at_wrong_pose():
    f = factory()
    f.create_product("red_block")
    f.transport.heartbeat(True, STATIONS["home"])
    f.transport.dispatch()
    t = f.transport.active
    before = f.energy.battery.remaining_wh
    f.transport.heartbeat(True, STATIONS["charging_dock"], motion(1, 1))
    assert f.energy.battery.remaining_wh < before
    f.transport.heartbeat(True, STATIONS["home"])
    for status in ("accepted", "navigating", "delivered"):
        f.transport.receive({**t.to_dict(), "status": status})
    assert f.energy.state == "blocked_energy"


def test_motion_replays_and_manager_restart():
    f = factory(0.9)
    h = f.transport.heartbeat
    h(True, STATIONS["home"], motion(1, 2, 1))
    remaining = f.energy.battery.remaining_wh
    h(True, STATIONS["home"], motion(1, 2, 1))
    h(True, STATIONS["home"], motion(0, 0))
    h(True, STATIONS["home"], motion(1, 1, session="new"))
    h(True, STATIONS["home"], motion(2, 100, session="test"))
    assert f.energy.battery.remaining_wh == remaining
    h(True, STATIONS["home"], motion(2, 2, session="new"))
    assert f.energy.battery.remaining_wh < remaining


def test_motion_invalid_counter_fails_without_battery_mutation():
    f = factory()
    before = f.energy.battery.remaining_wh
    for data in (motion(1, math.nan), motion(1, 0, 1), motion(1, -1)):
        with pytest.raises(ValueError):
            f.transport.heartbeat(True, STATIONS["home"], data)
    assert f.energy.battery.remaining_wh == before


def test_loaded_fault_energy_hold_does_not_create_charger_goal():
    f, p, old = transit()
    f.energy.battery.remaining_wh = 5.1
    fault(f)
    acknowledge(f)
    assert f.transport.active is old and old.payload_loaded
    assert f.energy.state == "critical_energy"
    assert p.current_location == "vision"


def test_normal_loaded_delivery_does_not_charge_at_planning_reserve():
    f, _, task = transit()
    f.energy.battery.remaining_wh = 19
    f.transport.heartbeat(True, STATIONS["vision"], motion(1, 1))
    assert f.transport.active is task and not task.cancel_requested
    assert f.energy.state == "ready"


def test_unsafe_loaded_delivery_cancels_before_advancing():
    f, p, task = transit()
    f.energy.battery.remaining_wh = 5.1
    f.transport.heartbeat(True, STATIONS["vision"], motion(1, 1))
    assert task.cancel_requested and f.energy.state == "critical_energy"
    assert p.current_location == "vision"


def test_impossible_mission_and_unreachable_charger_fail_closed():
    f = factory(0.21)
    f.energy.battery = Battery(replace(f.energy.battery.config, capacity_wh=1))
    assert not f.energy.authorize("P", "input_queue", "vision", STATIONS["home"])
    assert f.energy.state == "blocked_energy"
    f = factory(0.05)
    assert not f.energy.begin_charge_trip(STATIONS["home"])
    assert f.energy.state == "critical_energy"


def test_json_and_ros_mapping():
    f, _, task = charging_factory()
    decoded = TransportRequest.from_dict(json.loads(json.dumps(task.to_dict())), STATIONS)
    assert decoded.mission_type == "charge" and decoded.phase == "delivery"
    assert not decoded.payload_loaded
    fields = battery_ros_fields(f.energy.snapshot())
    assert fields["percentage"] == pytest.approx(0.21)
    assert math.isnan(fields["voltage"]) and fields["present"]
    json.dumps(f.snapshot(), allow_nan=False)


def test_browser_logical_charge_and_resume():
    f = factory(mode="simulated")
    p = f.create_product("red_block")
    for _ in range(200):
        f.tick()
        if p.status == ProductStatus.COMPLETED:
            break
    assert p.status == ProductStatus.COMPLETED
    assert f.energy.charge_cycles == 1
    assert f.transport is None
    assert any(e.event_type == "charge_completed" for e in f.events)


def test_environment_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("AMR_INITIAL_SOC", "0.23")
    assert BatteryConfig.load(tmp_path).initial_soc == 0.23


def test_charger_uses_single_existing_nav2_goal():
    client, events = MockClient(), []
    runner = NavigationRunner(STATIONS, client, lambda p: p, events.append)
    task = TransportRequest(
        "AMR", "home", "charging_dock", mission_type="charge", phase="delivery"
    )
    runner.submit(task.to_dict())
    assert client.goals == [STATIONS["charging_dock"]]
    assert runner.task.status == "navigating" and not runner.task.payload_loaded
    client.handles[0].result.set_result(SimpleNamespace(status=4))
    assert runner.task.status == "delivered"
    assert len(client.goals) == 1 and not events[-1]["payload_loaded"]


def test_deferred_destination_revalidated_after_charge():
    f = factory(0.21)
    p = f.create_product("red_block")
    f.tracker.move(p.product_id, "vision")
    p.completed_processes.append("visual_inspection")
    p.status = ProductStatus.QUEUED
    f.transport.heartbeat(True, STATIONS["vision"])
    f.transport.dispatch()
    task = f.transport.active
    assert task.mission_type == "charge"
    from reconfactory.models import FaultType

    f.inject_fault("station_a", FaultType.OVERHEAT)
    f.transport.heartbeat(True, STATIONS["charging_dock"])
    for status in ("accepted", "navigating", "delivered"):
        f.transport.receive({**task.to_dict(), "status": status})
    f.transport.heartbeat(True, STATIONS["charging_dock"], motion(1, 40))
    f.transport.dispatch()
    assert f.transport.active.destination == "station_b"
    assert p.current_location == "vision"


def test_energy_events_persist_once_with_mission_accounting(tmp_path):
    f = factory()
    f.logger = DataLogger(tmp_path / "energy.db")
    f.create_product("red_block")
    f.transport.heartbeat(True, STATIONS["home"])
    for _ in range(10):
        f.transport.dispatch()
    task = f.transport.active
    f.transport.heartbeat(True, STATIONS["charging_dock"], motion(1, 5, 1.3))
    for status in ("accepted", "navigating", "delivered"):
        f.transport.receive({**task.to_dict(), "status": status})
    for _ in range(10):
        f.transport.receive({**task.to_dict(), "status": "delivered"})
    f.transport.heartbeat(True, STATIONS["charging_dock"], motion(2, 45, 1.3))
    with sqlite3.connect(f.logger.db_path) as db:
        rows = db.execute("SELECT event_type, data_json FROM events").fetchall()
    records = {kind: json.loads(data) for kind, data in rows}
    for kind in (
        "charge_started",
        "charge_completed",
        "charging_mission_requested",
        "transport_deferred_for_energy",
    ):
        assert sum(k == kind for k, _ in rows) == 1
    result = records["transport_delivered"]
    assert result["actual_energy_wh"] > 0 and result["estimated_energy_wh"] > 0
    assert result["task_id"] == task.task_id and result["mission_type"] == "charge"
    assert records["charge_completed"]["charging_seconds"] == 40


def test_energy_experiment_reproducible_and_reports_unfinished_work():
    from scripts.compare_energy_policies import run

    baseline, aware = run(False), run(True)
    assert baseline["critical_stops"] == 1
    assert baseline["completion_time_s"] is None and baseline["unfinished_products"] > 0
    assert aware["unfinished_products"] == 0 and aware["energy"]["charge_cycles"] == 1
    assert aware["energy"]["charging_seconds"] > 1
    assert aware == run(True)
