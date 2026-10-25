import copy
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from reconfactory import FactorySupervisor
from reconfactory.actuator_watchdog import recovery_allowed, validate_observation
from reconfactory.logger import DataLogger


def test_robot_has_no_bridge_bypass_and_plugin_build_precedes_gazebo():
    import yaml

    root = Path(__file__).resolve().parents[1]
    package = root / "ros2_ws/src/reconfactory_amr"
    robot = ET.parse(package / "urdf/amr.urdf.xacro").getroot()
    drive = robot.find("gazebo/plugin[@name='gz::sim::systems::DiffDrive']")
    watchdog = robot.find("gazebo/plugin[@name='reconfactory::ActuatorWatchdog']")
    assert watchdog is not None
    assert drive.findtext("topic") == "/amr/actuator_cmd_vel"
    bridges = yaml.safe_load((package / "config/bridge.yaml").read_text())
    commands = [b for b in bridges if b["ros_topic_name"] == "/cmd_vel"]
    assert len(commands) == 1
    assert commands[0]["gz_topic_name"] == "/amr/cmd_vel_requested"
    assert all(
        b["direction"] == "GZ_TO_ROS"
        for b in bridges
        if b["gz_topic_name"] == "/amr/actuator_cmd_vel"
    )
    launcher = (root / "run_ubuntu.sh").read_text()
    assert launcher.index("colcon build --packages-up-to reconfactory_amr") < launcher.index(
        "setsid gz sim"
    )


def observation():
    return {
        "state": "FAULT_LATCHED",
        "instance_id": "test",
        "sample_sequence": 1,
        "robot_stopped_confirmed": True,
        "events": [
            {
                "event_id": "test:1",
                "event_type": "actuator_watchdog_timeout",
                "reason": "timeout",
            }
        ],
    }


def test_observation_persists_once_and_expires(tmp_path):
    f = FactorySupervisor(transport_mode="amr", enable_database=False, maintenance_mode="rules")
    f.logger = DataLogger(tmp_path / "watchdog.db")
    state = observation()
    f.transport.observe_actuator(state)
    f.transport.actuator_received_at = 0
    f.transport.observe_actuator(state)
    assert not f.transport.actuator_snapshot()["fresh"], "Replay must not refresh state"
    state["sample_sequence"] = 2
    f.transport.observe_actuator(state)
    assert f.transport.actuator_snapshot()["state"] == "FAULT_LATCHED"
    assert f.transport.active is None and not f.running
    with sqlite3.connect(f.logger.db_path) as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM events WHERE event_type='actuator_watchdog_timeout'"
            ).fetchone()[0]
            == 1
        )
    f.transport.actuator_received_at = 0
    assert not f.transport.actuator_snapshot()["robot_stopped_confirmed"]
    assert f.transport.actuator_snapshot()["state"] == "UNAVAILABLE"


@pytest.mark.parametrize(
    "key,value",
    [
        ("state", "bad"),
        ("state", []),
        ("instance_id", ""),
        ("sample_sequence", True),
        ("sample_sequence", -1),
        ("events", [{"event_type": "other"}]),
    ],
)
def test_invalid_observation(key, value):
    state = observation()
    state[key] = value
    with pytest.raises(ValueError):
        validate_observation(state)


def recovery_inputs():
    return dict(
        backend={"running": False, "emergency_active": False, "active_task": None},
        gate={
            "safety_state": "DISARMED",
            "robot_stopped_confirmed": True,
            "odometry_fresh": True,
        },
        lease={"mode": "DISARMED", "reset_eligible": True},
        watchdog=observation(),
        observations_fresh=True,
        nav_idle=True,
        stopped=True,
    )


def test_valid_recovery_contract():
    assert recovery_allowed(**recovery_inputs())


@pytest.mark.parametrize("key", ["observations_fresh", "nav_idle", "stopped"])
def test_recovery_requires_fresh_idle_stopped(key):
    args = recovery_inputs()
    args[key] = False
    assert not recovery_allowed(**args)


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("backend", "running", True),
        ("backend", "emergency_active", True),
        ("backend", "active_task", {"status": "failed"}),
        ("gate", "safety_state", "AUTHORIZED"),
        ("gate", "safety_state", "FAULT_LATCHED"),
        ("gate", "odometry_fresh", False),
        ("lease", "reset_eligible", False),
        ("watchdog", "robot_stopped_confirmed", False),
    ],
)
def test_unreconciled_recovery_rejected(section, key, value):
    args = copy.deepcopy(recovery_inputs())
    args[section][key] = value
    assert not recovery_allowed(**args)
