"""Fault replanning contracts and Nav2 races without a ROS installation."""

import json
import sqlite3
from concurrent.futures import Future
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_amr_transport import STATIONS, MockClient, NavigationRunner
from test_gazebo_sync import load_sync_module

from reconfactory import FactorySupervisor
from reconfactory.logger import DataLogger
from reconfactory.models import FaultType, ProductStatus
from reconfactory.transport import TransportRequest


def transit(phase="delivery", status="navigating", **kwargs):
    f = FactorySupervisor(
        enable_database=False,
        transport_mode="amr",
        vision_source="synthetic",
        maintenance_mode="rules",
        **kwargs,
    )
    f.start()
    p = f.create_product("red_block")
    f.tracker.move(p.product_id, "vision")
    p.completed_processes.append("visual_inspection")
    p.status = ProductStatus.QUEUED
    f.transport.heartbeat(True)
    f.transport.dispatch()
    task = f.transport.active
    assert task.destination == "station_a"
    if status != "requested":
        f.transport.receive({**task.to_dict(), "status": "accepted"})
    if status == "navigating":
        f.transport.receive({**task.to_dict(), "status": "navigating"})
        if phase == "delivery":
            f.transport.receive({**task.to_dict(), "phase": "delivery"})
    return f, p, task


def fault(f):
    f.inject_fault(f.transport.active.destination, FaultType.OVERHEAT)


def acknowledge(f):
    f.transport.receive({**f.transport.active.to_dict(), "status": "cancelled"})
    f.transport.heartbeat(True)
    f.transport.dispatch()


@pytest.mark.parametrize(
    "status,phase",
    [
        ("requested", "pickup"),
        ("accepted", "pickup"),
        ("navigating", "pickup"),
        ("navigating", "delivery"),
    ],
)
def test_fault_waits_for_ack_then_replans(status, phase):
    f, p, old = transit(phase, status)
    fault(f)
    f.transport.dispatch()
    assert f.transport.active is old and old.cancel_requested
    assert old.replan_state == "cancelling"
    acknowledge(f)
    new = f.transport.active
    assert new.destination == "station_b" and new.supersedes_task_id == old.task_id
    assert new.phase == phase and new.payload_loaded == (phase == "delivery")
    assert p.current_location == "vision" and p.status == ProductStatus.IN_TRANSIT
    assert f.stations["station_b"].current_product_id is None
    assert json.loads(json.dumps(new.to_dict()))["fault_id"]


def test_duplicate_fault_cancel_and_late_delivery():
    f, p, old = transit()
    fault(f)
    f.transport.invalidate_destination(old.destination, "duplicate")
    with pytest.raises(ValueError, match="cancellation"):
        f.transport.receive({**old.to_dict(), "status": "delivered"})
    acknowledge(f)
    new = f.transport.active
    f.transport.receive({**old.to_dict(), "status": "cancelled"})
    with pytest.raises(ValueError):
        f.transport.receive({**old.to_dict(), "status": "delivered"})
    assert f.transport.active is new and p.current_location == "vision"
    assert sum(e.event_type == "transport_replanned" for e in f.events) == 1


@pytest.mark.parametrize("outcome", ["delivered", "failed", "cancelled"])
def test_replacement_only_success_advances(outcome):
    f, p, _ = transit()
    fault(f)
    acknowledge(f)
    new = f.transport.active
    for status in ("accepted", "navigating", outcome):
        f.transport.receive({**new.to_dict(), "status": status})
    assert (p.current_location == "station_b") == (outcome == "delivered")
    assert (f.stations["station_b"].current_product_id == p.product_id) == (
        outcome == "delivered"
    )


@pytest.mark.parametrize("unavailable", ["fault", "incapable", "occupied"])
def test_no_alternative_holds_payload(unavailable):
    f, p, old = transit()
    if unavailable == "fault":
        f.inject_fault("station_b", FaultType.OVERHEAT)
    elif unavailable == "incapable":
        f.stations["station_b"].config.capabilities.clear()
    else:
        other = f.create_product("red_block")
        f.tracker.move(other.product_id, "station_b")
    fault(f)
    acknowledge(f)
    assert f.transport.active is old and old.replan_state == "awaiting_replan"
    assert old.payload_loaded and p.current_location == "vision"
    assert p.status == ProductStatus.IN_TRANSIT
    if unavailable == "fault":
        f.recover_machine("station_b")
        f.transport.dispatch()
        assert f.transport.active.destination == "station_b"


def test_fault_after_delivery_does_not_replan_completed_task():
    f, _, old = transit()
    f.transport.receive({**old.to_dict(), "status": "delivered"})
    f.inject_fault("station_a", FaultType.OVERHEAT)
    assert not old.cancel_requested
    assert not any(e.event_type == "transport_replan_requested" for e in f.events)


def test_health_does_not_cancel_but_selects_replacement():
    f, _, old = transit(health_scheduling=True)
    f._update_machine_health()
    a = f.stations["station_a"]
    a.health_prediction = replace(a.health_prediction, status="critical", anomaly_score=1)
    f.transport.check_timeout()
    assert not old.cancel_requested
    fault(f)
    f.transport.receive({**old.to_dict(), "status": "cancelled"})
    # Both become valid again before dispatch; prefer lower-risk B via existing policy.
    f.recover_machine("station_a")
    a.health_prediction = replace(a.health_prediction, status="critical", anomaly_score=1)
    f.transport.dispatch()
    assert f.transport.active.destination == "station_b"


def test_replacement_fault_before_dispatch_does_not_issue_goal():
    f, _, old = transit()
    fault(f)
    f.inject_fault("station_b", FaultType.OVERHEAT)
    acknowledge(f)
    assert f.transport.active is old


def test_unavailable_heartbeat_never_replans():
    f, _, old = transit()
    fault(f)
    f.transport.receive({**old.to_dict(), "status": "cancelled"})
    f.transport.heartbeat(False)
    f.transport.dispatch()
    assert f.transport.active is old


def runner(stopped=lambda: True):
    client, events = MockClient(), []
    nav = NavigationRunner(STATIONS, client, lambda p: p, events.append, stopped=stopped)
    request = TransportRequest(
        "P-test",
        "vision",
        "station_a",
        payload_loaded=True,
        phase="delivery",
        supersedes_task_id="old",
    )
    nav.submit(request.to_dict())
    return nav, client, events


def test_loaded_replacement_skips_pickup_and_waits_for_stop():
    stop = [False]
    nav, client, events = runner(lambda: stop[0])
    assert client.goals == [STATIONS["station_a"]]
    nav.cancel()
    nav.cancel()
    assert client.handles[0].cancel_count == 1
    client.handles[0].result.set_result(SimpleNamespace(status=5))
    assert nav.task.status == "navigating"
    stop[0] = True
    nav.watchdog()
    assert events[-1]["status"] == "cancelled" and events[-1]["payload_loaded"]


def test_cancel_acceptance_is_not_completion():
    nav, client, _ = runner()
    ack = Future()
    client.handles[0].cancel_goal_async = lambda: ack
    nav.cancel()
    ack.set_result(SimpleNamespace(return_code=0, goals_canceling=["goal"]))
    assert nav.task.status == "navigating"
    with pytest.raises(ValueError, match="busy"):
        nav.submit(TransportRequest("P-other", "vision", "station_b").to_dict())
    client.handles[0].result.set_result(SimpleNamespace(status=5))
    assert nav.task.status == "cancelled"


@pytest.mark.parametrize("exception", [False, True])
def test_cancel_rejection_or_error_blocks_replacement(exception):
    nav, client, _ = runner()
    ack = Future()
    client.handles[0].cancel_goal_async = lambda: ack
    nav.cancel()
    if exception:
        ack.set_exception(RuntimeError("connection lost"))
    else:
        ack.set_result(SimpleNamespace(return_code=1, goals_canceling=[]))
    assert nav.task.status == "failed" and nav.uncertain
    with pytest.raises(ValueError, match="uncertain"):
        nav.submit(TransportRequest("P-other", "vision", "station_b").to_dict())


def test_local_success_before_http_acceptance_is_invalidated():
    nav, client, events = runner()
    client.handles[0].result.set_result(SimpleNamespace(status=4))
    assert nav.task.status == "delivered"
    nav.cancel(invalidate_delivery=True)
    assert events[-1]["status"] == "cancelled"


def test_gazebo_payload_never_rolls_back_during_replanning():
    f, p, old = transit()
    sync = load_sync_module()
    bridge = sync.GazeboSync(backend_url="", world="test", interval=0.04, dry_run=True)
    bridge.amr_surfaces = {"vision": sync.Pose(2, 1.8, 1, 0)}
    f.transport.heartbeat(True, {"x": 3.2, "y": 0.7, "z": 0.2, "yaw": 0})

    def check():
        bridge.sync_amr_products(f.snapshot())
        pose = bridge.product_poses[bridge.product_model_name(p.product_id)]
        assert pose.x == 3.2 and pose.z == pytest.approx(0.39)

    check()
    fault(f)
    check()
    f.transport.receive({**old.to_dict(), "status": "cancelled"})
    check()
    f.transport.dispatch()
    check()


def test_cancel_failure_does_not_become_automatic_replan():
    f, p, old = transit()
    fault(f)
    f.transport.receive({**old.to_dict(), "status": "failed", "failure_reason": "lost handle"})
    f.transport.dispatch()
    assert f.transport.active is old and old.replan_state == "blocked_transport"
    assert p.current_location == "vision"


def test_paired_experiment_same_fault_and_measured_outcome():
    from analytics.replanning_experiment import run_replanning_comparison

    result = run_replanning_comparison()
    baseline, replan = result["static"], result["replanning"]
    assert baseline["fault_tick"] == replan["fault_tick"]
    assert baseline["successful_replans"] == 0 and baseline["recovery_ticks"] is None
    assert baseline["stranded_products"] == 1 and baseline["completion_tick"] is None
    assert replan["completed_products"] == 1 and replan["successful_replans"] == 1
    assert (
        replan["recovery_ticks"]
        >= replan["cancel_latency_ticks"] + replan["replan_latency_ticks"]
    )


def test_sqlite_replanning_events_are_linked_and_not_flooded(tmp_path):
    f, _, old = transit()
    f.logger = DataLogger(tmp_path / "replan.db")
    fault(f)
    acknowledge(f)
    for _ in range(10):
        f.transport.dispatch()
    with sqlite3.connect(f.logger.db_path) as db:
        rows = db.execute(
            "SELECT event_type, data_json FROM events WHERE event_type LIKE 'transport_%'"
        ).fetchall()
    records = {kind: json.loads(data) for kind, data in rows}
    assert sum(kind == "transport_replanned" for kind, _ in rows) == 1
    assert records["transport_replanned"]["supersedes_task_id"] == old.task_id
    assert records["transport_goal_cancelled"]["cancel_latency_s"] >= 0


def test_terminal_cancel_response_race_waits_for_result():
    nav, client, _ = runner()
    ack = Future()
    client.handles[0].cancel_goal_async = lambda: ack
    nav.cancel()
    ack.set_result(SimpleNamespace(return_code=3, goals_canceling=[]))
    assert nav.task.status == "navigating"
    client.handles[0].result.set_result(SimpleNamespace(status=4))
    assert nav.task.status == "cancelled"
