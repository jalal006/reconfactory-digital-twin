"""Observation/recovery contracts; no ROS dependency and no motion authority."""

STATES = {"STARTUP_INHIBITED", "ARMED", "FAULT_LATCHED"}


def validate_observation(state):
    if not isinstance(state.get("state"), str) or state["state"] not in STATES:
        raise ValueError("Invalid actuator watchdog state")
    if not isinstance(state.get("instance_id"), str) or not state["instance_id"]:
        raise ValueError("Missing watchdog instance")
    if type(state.get("sample_sequence")) is not int or state["sample_sequence"] < 1:
        raise ValueError("Invalid watchdog sample sequence")
    events = state.get("events", [])
    if not isinstance(events, list) or len(events) > 64:
        raise ValueError("Invalid actuator event history")
    for event in events:
        if (
            not isinstance(event, dict)
            or not isinstance(event.get("event_type"), str)
            or not event["event_type"].startswith("actuator_watchdog_")
            or not isinstance(event.get("event_id"), str)
            or not event["event_id"]
        ):
            raise ValueError("Invalid actuator event")


def recovery_allowed(backend, gate, lease, watchdog, *, observations_fresh, nav_idle, stopped):
    return bool(
        observations_fresh
        and nav_idle
        and stopped
        and watchdog.get("state") == "FAULT_LATCHED"
        and watchdog.get("robot_stopped_confirmed") is True
        and gate.get("safety_state") == "DISARMED"
        and gate.get("robot_stopped_confirmed") is True
        and gate.get("odometry_fresh") is True
        and lease.get("mode") == "DISARMED"
        and lease.get("reset_eligible") is True
        and not backend.get("running", True)
        and not backend.get("emergency_active", True)
        and backend.get("active_task") is None
    )
