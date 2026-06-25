"""Machine-state transition rules."""

from __future__ import annotations

from .models import MachineState

VALID_TRANSITIONS: dict[MachineState, set[MachineState]] = {
    MachineState.OFFLINE: {
        MachineState.STARTING,
        MachineState.MAINTENANCE,
        MachineState.FAULT,
        MachineState.EMERGENCY_STOP,
    },
    MachineState.STARTING: {
        MachineState.IDLE,
        MachineState.FAULT,
        MachineState.EMERGENCY_STOP,
    },
    MachineState.IDLE: {
        MachineState.RUNNING,
        MachineState.PAUSED,
        MachineState.FAULT,
        MachineState.MAINTENANCE,
        MachineState.OFFLINE,
        MachineState.EMERGENCY_STOP,
    },
    MachineState.RUNNING: {
        MachineState.IDLE,
        MachineState.PAUSED,
        MachineState.BLOCKED,
        MachineState.FAULT,
        MachineState.EMERGENCY_STOP,
    },
    MachineState.PAUSED: {
        MachineState.IDLE,
        MachineState.RUNNING,
        MachineState.FAULT,
        MachineState.EMERGENCY_STOP,
    },
    MachineState.BLOCKED: {
        MachineState.IDLE,
        MachineState.FAULT,
        MachineState.EMERGENCY_STOP,
    },
    MachineState.FAULT: {
        MachineState.RECOVERING,
        MachineState.MAINTENANCE,
        MachineState.EMERGENCY_STOP,
    },
    MachineState.MAINTENANCE: {
        MachineState.RECOVERING,
        MachineState.OFFLINE,
        MachineState.EMERGENCY_STOP,
    },
    MachineState.RECOVERING: {
        MachineState.IDLE,
        MachineState.FAULT,
        MachineState.EMERGENCY_STOP,
    },
    MachineState.EMERGENCY_STOP: {
        MachineState.RECOVERING,
        MachineState.OFFLINE,
    },
}


class InvalidStateTransition(ValueError):
    """Raised when a station receives an invalid state transition."""


class MachineStateMachine:
    def __init__(self, initial_state: MachineState = MachineState.OFFLINE) -> None:
        self.state = initial_state

    def can_transition(self, target: MachineState) -> bool:
        return target == self.state or target in VALID_TRANSITIONS[self.state]

    def transition(self, target: MachineState) -> None:
        if target == self.state:
            return
        if not self.can_transition(target):
            raise InvalidStateTransition(
                f"Cannot transition from {self.state.value} to {target.value}"
            )
        self.state = target

    def emergency_stop(self) -> None:
        self.transition(MachineState.EMERGENCY_STOP)
