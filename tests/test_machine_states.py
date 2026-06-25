import pytest

from reconfactory.config import DEFAULT_MACHINE_CONFIGS
from reconfactory.models import FaultType, MachineState
from reconfactory.state_machine import InvalidStateTransition, MachineStateMachine
from reconfactory.stations import StationController


def test_station_moves_from_offline_to_idle_and_processes_product():
    station = StationController(DEFAULT_MACHINE_CONFIGS["station_a"])

    station.start()
    assert station.state == MachineState.IDLE

    station.assign("P-00001", "drill")
    assert station.state == MachineState.RUNNING

    completed = None
    for _ in range(3):
        completed = station.tick()

    assert completed is not None
    assert completed.product_id == "P-00001"
    assert completed.process == "drill"
    assert station.state == MachineState.IDLE
    assert station.current_product_id is None


def test_invalid_state_transition_is_rejected():
    machine = MachineStateMachine(MachineState.OFFLINE)

    with pytest.raises(InvalidStateTransition):
        machine.transition(MachineState.RUNNING)


def test_fault_and_recovery_return_station_to_idle():
    station = StationController(DEFAULT_MACHINE_CONFIGS["station_a"])
    station.start()

    station.inject_fault(FaultType.OVERHEAT)
    assert station.state == MachineState.FAULT
    assert not station.healthy

    station.recover()
    assert station.state == MachineState.IDLE
    assert station.healthy
