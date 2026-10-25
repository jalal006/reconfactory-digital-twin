import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_amr_safety import recovery_action  # noqa: E402


def observation(gate="FAULT_LATCHED", actuator="FAULT_LATCHED", ready=False):
    return {
        "safety": {"safety_state": gate},
        "actuator": {"state": actuator, "startup_ready": ready},
        "safety_at": 10.0,
        "actuator_at": 10.0,
        "odom_at": 10.0,
        "speed": 0.0,
        "angular": 0.0,
    }


def test_dual_latch_requires_gate_then_actuator_then_new_initialization():
    sample = observation()
    assert recovery_action(sample, 10.1) == "reset_gate"
    sample["safety"]["safety_state"] = "DISARMED"
    assert recovery_action(sample, 10.1) == "reset_actuator"
    sample["actuator"]["state"] = "STARTUP_INHIBITED"
    assert recovery_action(sample, 10.1) is None
    sample["actuator"]["startup_ready"] = True
    assert recovery_action(sample, 10.1) == "ready"


def test_manager_only_fault_does_not_reset_healthy_actuator():
    sample = observation(actuator="ARMED")
    assert recovery_action(sample, 10.1) == "reset_gate"
    sample["safety"]["safety_state"] = "DISARMED"
    assert recovery_action(sample, 10.1) == "ready"


@pytest.mark.parametrize("key", ["safety_at", "actuator_at", "odom_at"])
def test_stale_observation_cannot_authorize_recovery(key):
    sample = observation("DISARMED", "ARMED")
    sample[key] = 9.0
    assert recovery_action(sample, 10.1) is None


@pytest.mark.parametrize("gate", ["AUTHORIZED", "CONTROLLED_HOLD", "UNAVAILABLE"])
def test_actuator_reset_requires_disarmed_gate(gate):
    assert recovery_action(observation(gate), 10.1) is None


@pytest.mark.parametrize(
    "key,value", [("speed", 0.04), ("angular", 0.1), ("speed", float("nan"))]
)
def test_moving_or_invalid_odometry_blocks_recovery(key, value):
    sample = observation()
    sample[key] = value
    assert recovery_action(sample, 10.1) is None
