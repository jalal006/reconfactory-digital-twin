import json
import math
import sqlite3

import pytest

from reconfactory.amr_safety import ZERO, MotionSafety, SafetyConfig


def setup():
    now = [0.0]
    gate = MotionSafety(clock=lambda: now[0])
    gate.odometry(0, 0)
    return gate, now


def lease(
    seq=1,
    mode="AUTHORIZED",
    task="T1",
    session="M1",
    eligible=False,
    mission="production_transport",
):
    return dict(
        session_id=session,
        sequence=seq,
        mode=mode,
        task_id=task,
        mission_type=mission,
        reset_eligible=eligible,
    )


def test_startup_disarmed_and_zero():
    g, _ = setup()
    g.velocity((0.2, 0, 0, 0, 0, 0))
    assert g.state == "DISARMED" and g.tick() == ZERO


def test_readiness_requires_first_and_current_odometry():
    now = [0.0]
    gate = MotionSafety(clock=lambda: now[0])
    assert not gate.snapshot()["odometry_fresh"]
    gate.odometry(0, 0)
    assert gate.snapshot()["odometry_fresh"]
    now[0] = 0.51
    assert not gate.snapshot()["odometry_fresh"]
    assert gate.tick() == ZERO


def test_authorized_forwards_exact_command():
    g, _ = setup()
    assert g.lease(lease())
    cmd = (0.2, 0, 0, 0, 0, -0.3)
    g.velocity(cmd)
    assert g.tick() == cmd


def test_expired_lease_latches_before_other_timeouts():
    g, now = setup()
    g.lease(lease())
    now[0] = 0.49
    g.odometry(0.2, 0)
    g.velocity((0.2, 0, 0, 0, 0, 0))
    now[0] = 0.51
    assert g.tick() == ZERO and g.state == "FAULT_LATCHED"
    assert "heartbeat" in g.reason
    assert not g.snapshot()["robot_stopped_confirmed"]


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_nonfinite_velocity_latches(bad):
    g, _ = setup()
    g.lease(lease())
    g.velocity((bad, 0, 0, 0, 0, 0))
    assert g.tick() == ZERO and g.state == "FAULT_LATCHED"


def test_stale_command_latches_with_fresh_lease_and_odom():
    g, now = setup()
    g.lease(lease())
    g.velocity((0.2, 0, 0, 0, 0, 0))
    now[0] = 0.2
    g.lease(lease(2))
    now[0] = 0.31
    g.odometry(0, 0)
    assert g.tick() == ZERO and "command timeout" in g.reason


def test_no_command_replay_after_hold():
    g, _ = setup()
    g.lease(lease())
    g.velocity((0.2, 0, 0, 0, 0, 0))
    g.lease(lease(2, "CONTROLLED_HOLD"))
    g.velocity((0.4, 0, 0, 0, 0, 0))
    assert g.tick() == ZERO
    g.lease(lease(3, task="T2"))
    assert g.tick() == ZERO and g.state == "AUTHORIZED"
    g.velocity((0.1, 0, 0, 0, 0, 0))
    assert g.tick()[0] == 0.1


def test_duplicate_lease_does_not_extend_freshness():
    g, now = setup()
    g.lease(lease())
    now[0] = 0.4
    assert not g.lease(lease())
    now[0] = 0.51
    assert g.tick() == ZERO and g.state == "FAULT_LATCHED"


def test_task_mismatch_latches():
    g, _ = setup()
    g.lease(lease())
    assert not g.lease(lease(2, task="T2"))
    assert g.state == "FAULT_LATCHED"


def test_retired_task_cannot_authorize_replacement():
    g, _ = setup()
    g.lease(lease())
    g.lease(lease(2, "CONTROLLED_HOLD"))
    g.lease(lease(3, task="T2"))
    g.lease(lease(4, "CONTROLLED_HOLD"))
    assert not g.lease(lease(5))
    assert g.state == "FAULT_LATCHED"


def test_manager_restart_does_not_clear_latch():
    g, now = setup()
    g.lease(lease())
    now[0] = 0.6
    g.tick()
    g.lease(lease(session="M2"))
    g.velocity((0.4, 0, 0, 0, 0, 0))
    assert g.tick() == ZERO and g.state == "FAULT_LATCHED"
    assert not g.lease(lease(100, session="M1"))


@pytest.mark.parametrize("case", ["moving", "stale_odom", "unreconciled", "stale_lease"])
def test_reset_rejects_invalid_conditions(case):
    g, now = setup()
    g.fault("test")
    now[0] = 0.35
    g.odometry(0.2 if case == "moving" else 0, 0)
    g.lease(lease(mode="DISARMED", eligible=case != "unreconciled"))
    if case in {"stale_odom", "stale_lease"}:
        now[0] = 1.0
        if case == "stale_odom":
            g.lease(lease(2, "DISARMED", eligible=True))
        else:
            g.odometry(0, 0)
    assert not g.reset()[0]
    assert g.state == "FAULT_LATCHED"


def test_eligible_explicit_reset_disarms_without_replay():
    g, now = setup()
    g.lease(lease())
    g.fault("backend outage")
    now[0] = 0.35
    g.odometry(0, 0)
    g.lease(lease(2, "DISARMED", eligible=True))
    assert g.reset()[0] and g.tick() == ZERO and g.state == "DISARMED"
    g.lease(lease(3, task="T2"))
    assert g.tick() == ZERO


def test_fresh_odom_stable_window_restarts_after_gap():
    g, now = setup()
    now[0] = 2
    g.odometry(0, 0)
    assert not g.stopped()
    now[0] += 0.31
    g.odometry(0, 0)
    assert g.stopped()


def test_stale_odom_latches_authorized_motion():
    g, now = setup()
    g.lease(lease())
    now[0] = 0.4
    g.lease(lease(2))
    now[0] = 0.51
    g.tick()
    assert g.state == "FAULT_LATCHED" and "Odometry" in g.reason


def test_controlled_hold_can_wait_without_fault():
    g, now = setup()
    g.lease(lease(mode="CONTROLLED_HOLD"))
    now[0] = 10
    assert g.tick() == ZERO and g.state == "CONTROLLED_HOLD"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        None,
        {"session_id": "M", "sequence": True, "mode": "AUTHORIZED"},
        lease(task=None),
        lease(mission="invalid"),
    ],
)
def test_invalid_lease_fails_closed(payload):
    g, _ = setup()
    assert not g.lease(payload)
    assert g.state == "FAULT_LATCHED"


def test_charge_navigation_has_same_gate():
    g, now = setup()
    g.lease(lease(mission="charge"))
    g.velocity((0.1, 0, 0, 0, 0, 0))
    assert g.tick()[0] == 0.1
    g.lease(lease(2, "CONTROLLED_HOLD", mission="charge"))
    now[0] = 20
    assert g.tick() == ZERO


def test_events_once_and_backend_stale_observation_not_stopped(tmp_path):
    from reconfactory import FactorySupervisor
    from reconfactory.logger import DataLogger

    f = FactorySupervisor(transport_mode="amr", enable_database=False, maintenance_mode="rules")
    f.logger = DataLogger(tmp_path / "safety.db")
    g, _ = setup()
    g.lease(lease())
    g.fault("test")
    for _ in range(10):
        g.tick()
        f.transport.observe_safety(g.snapshot(), list(g.events))
    assert sum(e.event_type == "amr_safety_fault_latched" for e in f.events) == 1
    with sqlite3.connect(f.logger.db_path) as connection:
        rows = connection.execute(
            "SELECT data_json FROM events WHERE event_type = 'amr_safety_fault_latched'"
        ).fetchall()
    assert len(rows) == 1
    assert json.loads(rows[0][0])["reason"] == "test"
    f.transport.safety_events.clear()  # Simulate a restart/eviction of the receipt cache.
    f.transport.observe_safety(g.snapshot(), list(g.events))
    with sqlite3.connect(f.logger.db_path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM events WHERE event_type = 'amr_safety_fault_latched'"
            ).fetchone()[0]
            == 1
        )
    json.dumps(f.snapshot(), allow_nan=False)
    f.transport.safety_received_at = 0
    assert not f.transport.safety_snapshot()["robot_stopped_confirmed"]
    assert not f.transport.safety_snapshot()["odometry_fresh"]
    assert f.transport.safety_snapshot()["safety_state"] == "UNAVAILABLE"


@pytest.mark.parametrize("value", [0, -1, math.nan, math.inf])
def test_invalid_safety_config(value):
    with pytest.raises(ValueError):
        SafetyConfig(lease_timeout_s=value)


def test_mission_type_cannot_change_under_existing_token():
    g, _ = setup()
    g.lease(lease())
    assert not g.lease(lease(2, mission="charge"))
    assert g.tick() == ZERO and g.state == "FAULT_LATCHED"


def test_initial_command_grace_never_permits_motion_and_expires():
    g, now = setup()
    g.lease(lease())
    for sequence in range(2, 24):
        now[0] += 0.1
        g.odometry(0, 0)
        g.lease(lease(sequence))
        assert g.tick() == ZERO
    assert g.state == "FAULT_LATCHED" and "first velocity" in g.reason


def test_latched_command_is_not_replayed_after_reset():
    g, now = setup()
    g.lease(lease())
    g.fault("manager lost")
    g.velocity((0.4, 0, 0, 0, 0, 0))
    now[0] = 0.35
    g.odometry(0, 0)
    g.lease(lease(2, "DISARMED", eligible=True))
    assert g.reset()[0]
    g.lease(lease(3, task="new"))
    assert g.tick() == ZERO
    g.velocity((0.1, 0, 0, 0, 0, 0))
    assert g.tick()[0] == 0.1


@pytest.mark.parametrize("kind", [None, 123, "unrelated_event"])
def test_invalid_observation_event_does_not_refresh_backend_state(kind):
    from reconfactory import FactorySupervisor

    f = FactorySupervisor(transport_mode="amr", enable_database=False, maintenance_mode="rules")
    g, _ = setup()
    with pytest.raises(ValueError):
        f.transport.observe_safety(g.snapshot(), [{"event_id": "bad", "event_type": kind}])
    assert not f.transport.safety_snapshot()["fresh"]
