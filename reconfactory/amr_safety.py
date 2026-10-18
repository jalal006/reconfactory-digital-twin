"""ROS-independent supervisory command gate; not certified functional safety."""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import asdict, dataclass
from uuid import uuid4

ZERO = (0.0,) * 6
STATES = {"DISARMED", "AUTHORIZED", "CONTROLLED_HOLD", "FAULT_LATCHED"}


@dataclass(frozen=True)
class SafetyConfig:
    lease_timeout_s: float = 0.5
    command_timeout_s: float = 0.3
    first_command_timeout_s: float = 2.0
    odometry_timeout_s: float = 0.5
    stopped_duration_s: float = 0.3
    linear_stop_m_s: float = 0.03
    angular_stop_rad_s: float = 0.05

    def __post_init__(self):
        if any(not math.isfinite(v) or v <= 0 for v in asdict(self).values()):
            raise ValueError("Safety thresholds must be finite and positive")


class MotionSafety:
    def __init__(self, config=None, clock=time.monotonic):
        self.config = config or SafetyConfig()
        self.clock = clock
        self.instance_id = uuid4().hex
        self.state = "DISARMED"
        self.reason = "No mission authorization"
        self.session = None
        self.sequence = -1
        self.retired_sessions = set()
        self.retired_tasks = set()
        self.task = None
        self.mission_type = None
        self.lease_at = None
        self.authorized_at = None
        self.command_at = None
        self.command = ZERO
        self.odom_at = None
        self.stopped_since = None
        self.reset_eligible = False
        self.last_fault_time = None
        self.inhibited_at = None
        self.stop_confirmed_at = None
        self.events = deque(maxlen=512)
        self.event_sequence = 0

    def event(self, kind, **data):
        self.event_sequence += 1
        self.events.append(
            {
                "event_id": f"{self.instance_id}:{self.event_sequence}",
                "event_type": kind,
                "task_id": self.task,
                "reason": self.reason,
                "state": self.state,
                "lease_timeout_s": self.config.lease_timeout_s,
                "mission_type": self.mission_type,
                "odometry_age_ms": (self.clock() - self.odom_at) * 1000
                if self.odom_at is not None
                else None,
                "heartbeat_age_ms": (self.clock() - self.lease_at) * 1000
                if self.lease_at is not None
                else None,
                **data,
            }
        )

    def transition(self, state, reason):
        if self.state == state:
            return
        previous = self.state
        self.state, self.reason = state, reason
        self.command_at, self.command = None, ZERO
        if state == "AUTHORIZED":
            self.authorized_at = self.clock()
            self.inhibited_at = self.stop_confirmed_at = None
        else:
            self.inhibited_at = self.clock()
            self.stop_confirmed_at = None
        if state == "FAULT_LATCHED":
            self.last_fault_time = time.time()
        self.event(
            {
                "AUTHORIZED": "amr_safety_authorized",
                "CONTROLLED_HOLD": "amr_safety_hold",
                "FAULT_LATCHED": "amr_safety_fault_latched",
                "DISARMED": "amr_safety_disarmed",
            }[state],
            previous_state=previous,
            new_state=state,
        )

    def fault(self, reason):
        self.transition("FAULT_LATCHED", reason)

    def lease(self, data):
        self.tick()
        try:
            session, sequence, mode = data["session_id"], data["sequence"], data["mode"]
            task, mission = data.get("task_id"), data.get("mission_type")
            if (
                not isinstance(session, str)
                or not session
                or len(session) > 128
                or type(sequence) is not int
                or sequence < 0
                or mode not in STATES
                or type(data.get("reset_eligible")) is not bool
            ):
                raise ValueError("Invalid lease schema")
            if mode == "AUTHORIZED" and (
                not isinstance(task, str)
                or not task
                or mission not in {"production_transport", "charge", "diagnostic"}
            ):
                raise ValueError("Invalid mission authorization")
        except (KeyError, TypeError, ValueError) as exc:
            self.fault(f"Invalid authorization: {exc}")
            return False
        if session in self.retired_sessions:
            return False
        if session != self.session:
            if self.session is not None:
                self.retired_sessions.add(self.session)
                if self.state == "AUTHORIZED":
                    self.fault("Manager session changed during authorization")
            self.session, self.sequence = session, -1
        if sequence <= self.sequence:
            return False
        self.sequence, self.lease_at = sequence, self.clock()
        self.reset_eligible = data["reset_eligible"] and mode == "DISARMED"
        if mode == "FAULT_LATCHED":
            self.fault(data.get("reason", "Manager reported unexpected loss of authority"))
        if self.state == "FAULT_LATCHED":
            return False
        if mode == "AUTHORIZED":
            if task == self.task and mission != self.mission_type:
                self.fault("Mission type changed for an existing task authorization")
                return False
            if task in self.retired_tasks or (self.state == "AUTHORIZED" and task != self.task):
                self.fault("Task changed without controlled hold, or retired task replay")
                return False
            if self.task and task != self.task:
                self.retired_tasks.add(self.task)
            self.task, self.mission_type = task, mission
            self.transition(mode, "Fresh manager authorization")
        else:
            self.transition(mode, data.get("reason", "Manager intentionally inhibited motion"))
        return True

    def velocity(self, values):
        self.tick()
        if len(values) != 6 or not all(math.isfinite(v) for v in values):
            self.fault("Non-finite or malformed velocity command")
            return
        if self.state == "AUTHORIZED":
            self.command, self.command_at = tuple(values), self.clock()

    def odometry(self, linear, angular):
        now = self.clock()
        if not all(math.isfinite(v) for v in (linear, angular)):
            self.stopped_since = None
            if self.state == "AUTHORIZED":
                self.fault("Invalid odometry")
            return
        if self.odom_at is None or now - self.odom_at >= self.config.odometry_timeout_s:
            self.stopped_since = None
        self.odom_at = now
        if (
            abs(linear) < self.config.linear_stop_m_s
            and abs(angular) < self.config.angular_stop_rad_s
        ):
            if self.stopped_since is None:
                self.stopped_since = now
        else:
            self.stopped_since = None

    def stopped(self):
        now = self.clock()
        return (
            self.odom_at is not None
            and now - self.odom_at < self.config.odometry_timeout_s
            and self.stopped_since is not None
            and now - self.stopped_since >= self.config.stopped_duration_s
        )

    def tick(self):
        now, c = self.clock(), self.config
        if self.state == "AUTHORIZED":
            if self.lease_at is None or now - self.lease_at >= c.lease_timeout_s:
                self.event(
                    "amr_safety_lease_expired",
                    expiry_detection_delay_s=now - self.lease_at - c.lease_timeout_s
                    if self.lease_at is not None
                    else None,
                )
                self.fault("Manager heartbeat timeout")
            elif self.odom_at is None or now - self.odom_at >= c.odometry_timeout_s:
                self.fault("Odometry timeout")
            elif self.command_at is not None and now - self.command_at >= c.command_timeout_s:
                self.fault("Velocity command timeout")
            elif (
                self.command_at is None
                and now - self.authorized_at >= c.first_command_timeout_s
            ):
                self.fault("No fresh first velocity command")
        if self.state != "AUTHORIZED" and self.stopped() and self.stop_confirmed_at is None:
            self.stop_confirmed_at = now
            self.event(
                "amr_safety_stop_confirmed",
                physical_stop_after_inhibition_s=now - self.inhibited_at
                if self.inhibited_at is not None
                else None,
            )
        return (
            self.command if self.state == "AUTHORIZED" and self.command_at is not None else ZERO
        )

    def reset(self):
        self.tick()
        self.event("amr_safety_reset_requested")
        valid = (
            self.state == "FAULT_LATCHED"
            and self.stopped()
            and self.reset_eligible
            and self.lease_at is not None
            and self.clock() - self.lease_at < self.config.lease_timeout_s
        )
        if not valid:
            self.event("amr_safety_reset_rejected", reset_result=False)
            return (
                False,
                "Require latched fault, fresh stopped odometry and reconciled idle manager/backend",
            )
        if self.task:
            self.retired_tasks.add(self.task)
        self.task = None
        self.transition("DISARMED", "Operator reset acknowledged; fresh mission required")
        self.event("amr_safety_reset_completed", reset_result=True)
        return True, self.reason

    def snapshot(self):
        self.tick()
        now = self.clock()
        return {
            "instance_id": self.instance_id,
            "safety_state": self.state,
            "safety_reason": self.reason,
            "current_task_id": self.task,
            "mission_type": self.mission_type,
            "heartbeat_age_ms": (now - self.lease_at) * 1000
            if self.lease_at is not None
            else None,
            "odometry_age_ms": (now - self.odom_at) * 1000
            if self.odom_at is not None
            else None,
            "odometry_fresh": self.odom_at is not None
            and now - self.odom_at < self.config.odometry_timeout_s,
            "command_inhibited": self.state != "AUTHORIZED" or self.command_at is None,
            "robot_stopped_confirmed": self.stopped(),
            "last_fault_time": self.last_fault_time,
            "reset_required": self.state == "FAULT_LATCHED",
            "physical_stop_after_inhibition_s": self.stop_confirmed_at - self.inhibited_at
            if self.stop_confirmed_at is not None and self.inhibited_at is not None
            else None,
        }
