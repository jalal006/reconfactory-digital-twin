"""Testable Nav2 action orchestration. Factory decisions stay in the supervisor."""

from __future__ import annotations

import time

from reconfactory.transport import TERMINAL, TaskRegistry, task_timeout_s


class NavigationRunner:
    def __init__(self, stations, client, goal_factory, publish, clock=time.monotonic):
        self.registry = TaskRegistry(stations)
        self.client = client
        self.goal_factory = goal_factory
        self.publish = publish
        self.clock = clock
        self.handle = None
        self.started = 0.0
        self.timeout_s = task_timeout_s()

    @property
    def task(self):
        return self.registry.active

    def submit(self, payload: dict) -> None:
        task = self.registry.receive(payload)
        self.started = self.clock()
        self._status("accepted")
        if not self.client.server_is_ready():
            self._status("failed", "Nav2 action server unavailable")
            return
        self._navigate(task.origin)

    def _status(self, status: str, reason: str | None = None, phase: str | None = None):
        payload = {
            **self.task.to_dict(),
            "status": status,
            "phase": phase or self.task.phase,
            "navigation_time_s": max(0.0, self.clock() - self.started),
            "failure_reason": reason,
        }
        if self.task.update(payload):
            self.publish(self.task.to_dict())

    def _navigate(self, station: str):
        self.handle = None
        try:
            future = self.client.send_goal_async(
                self.goal_factory(self.registry.stations[station])
            )
            future.add_done_callback(self._goal_response)
        except Exception as exc:
            self._status("failed", f"Cannot send Nav2 goal: {exc}")

    def _goal_response(self, future):
        try:
            self.handle = future.result()
            if not self.handle.accepted:
                self._status(
                    "cancelled" if self.task.cancel_requested else "failed",
                    "Nav2 rejected goal",
                )
                return
            self._status("navigating")
            self.handle.get_result_async().add_done_callback(self._result)
            if self.task.cancel_requested:
                self.handle.cancel_goal_async()
        except Exception as exc:
            self._status("failed", f"Nav2 goal response failed: {exc}")

    def _result(self, future):
        try:
            status = future.result().status
        except Exception as exc:
            self._status("failed", f"Nav2 result unavailable: {exc}")
            return
        # action_msgs/GoalStatus: SUCCEEDED=4, CANCELED=5. Only success advances.
        if self.task.cancel_requested or status == 5:
            self._status("cancelled", "Navigation cancelled; inspect payload before reset")
        elif status != 4:
            self._status("failed", f"Nav2 ended with action status {status}")
        elif self.task.phase == "pickup":
            self._status("navigating", phase="delivery")
            self._navigate(self.task.destination)
        else:
            self._status("delivered")

    def cancel(self):
        if self.task and self.task.status not in TERMINAL:
            self.task.cancel_requested = True
            if self.handle and self.handle.accepted:
                self.handle.cancel_goal_async()

    def watchdog(self):
        if (
            self.task
            and self.task.status not in TERMINAL
            and self.clock() - self.started > self.timeout_s
        ):
            self.cancel()
