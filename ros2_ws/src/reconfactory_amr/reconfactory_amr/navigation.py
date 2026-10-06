"""Testable Nav2 action orchestration. Factory decisions stay in the supervisor."""

from __future__ import annotations

import time

from reconfactory.transport import TERMINAL, TaskRegistry, task_timeout_s


class NavigationRunner:
    def __init__(
        self,
        stations,
        client,
        goal_factory,
        publish,
        clock=time.monotonic,
        stopped=lambda: True,
    ):
        self.registry = TaskRegistry(stations)
        self.client = client
        self.goal_factory = goal_factory
        self.publish = publish
        self.clock = clock
        self.handle = None
        self.started = 0.0
        self.timeout_s = task_timeout_s()
        self.stopped = stopped
        self.cancel_sent = False
        self.pending_cancel_result = False
        self.uncertain = False
        self.generation = 0

    @property
    def task(self):
        return self.registry.active

    def submit(self, payload: dict) -> None:
        if self.uncertain:
            raise ValueError("Navigation state uncertain; restart stack after inspecting robot")
        task = self.registry.receive(payload)
        self.started = self.clock()
        self.cancel_sent = False
        self.pending_cancel_result = False
        self.uncertain = False
        self._status("accepted")
        if not self.client.server_is_ready():
            self._status("failed", "Nav2 action server unavailable")
            return
        self._navigate(
            task.destination
            if task.payload_loaded or task.mission_type == "charge"
            else task.origin
        )

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
        self.cancel_sent = False
        self.generation += 1
        generation = self.generation
        try:
            future = self.client.send_goal_async(
                self.goal_factory(self.registry.stations[station])
            )
            future.add_done_callback(
                lambda result: (
                    self._goal_response(result) if generation == self.generation else None
                )
            )
        except Exception as exc:
            self.uncertain = True
            self._status("failed", f"Cannot send Nav2 goal: {exc}")

    def _goal_response(self, future):
        try:
            self.handle = future.result()
            if not self.handle.accepted:
                if self.task.cancel_requested:
                    self.pending_cancel_result = True
                    self._confirm_stop()
                else:
                    self._status("failed", "Nav2 rejected goal")
                return
            self._status("navigating")
            generation = self.generation
            self.handle.get_result_async().add_done_callback(
                lambda result: self._result(result) if generation == self.generation else None
            )
            if self.task.cancel_requested:
                self.cancel()
        except Exception as exc:
            self.uncertain = True
            self._status("failed", f"Nav2 goal response failed: {exc}")

    def _result(self, future):
        try:
            status = future.result().status
        except Exception as exc:
            self.uncertain = True
            self._status("failed", f"Nav2 result unavailable: {exc}")
            return
        # action_msgs/GoalStatus: SUCCEEDED=4, CANCELED=5. Only success advances.
        if self.task.cancel_requested or status == 5:
            # A terminal action result proves the old goal is no longer executing.
            # Success racing with invalidation is NOT a factory delivery.
            self.pending_cancel_result = True
            self._confirm_stop()
        elif status != 4:
            self._status("failed", f"Nav2 ended with action status {status}")
        elif self.task.phase == "pickup":
            self._status("navigating", phase="delivery")
            self._navigate(self.task.destination)
        else:
            self._status("delivered")

    def cancel(self, invalidate_delivery=False):
        if self.task and self.task.status == "delivered" and invalidate_delivery:
            # Local success can precede HTTP delivery acceptance. The supervisor
            # can still invalidate it; Nav2 has ended, but confirm physical stop.
            self.task.status = "navigating"
            self.task.completed_at = None
            self.task.cancel_requested = True
            self.pending_cancel_result = True
            self._confirm_stop()
            return
        if self.task and self.task.status not in TERMINAL:
            self.task.cancel_requested = True
            if self.handle and self.handle.accepted and not self.cancel_sent:
                self.cancel_sent = True
                try:
                    generation = self.generation
                    self.handle.cancel_goal_async().add_done_callback(
                        lambda result: (
                            self._cancel_response(result)
                            if generation == self.generation
                            else None
                        )
                    )
                except Exception as exc:
                    self.uncertain = True
                    self._status("failed", f"Nav2 cancellation unavailable: {exc}")

    def _cancel_response(self, future):
        if self.task.status in TERMINAL or self.pending_cancel_result:
            return
        try:
            response = future.result()
            if response.return_code == 3:
                return  # Already terminal: its result callback still must confirm stop.
            if response.return_code != 0 or not response.goals_canceling:
                raise RuntimeError("Nav2 refused cancellation")
            # Acceptance is not completion: wait for the terminal action result.
        except Exception as exc:
            self.uncertain = True
            self._status("failed", f"Cancellation not confirmed: {exc}")

    def _confirm_stop(self):
        if self.pending_cancel_result and self.stopped():
            self.pending_cancel_result = False
            self._status("cancelled", "Old navigation ended and robot stopped")

    def watchdog(self):
        self._confirm_stop()
        if (
            self.task
            and self.task.status not in TERMINAL
            and self.clock() - self.started > self.timeout_s
        ):
            self.cancel()
