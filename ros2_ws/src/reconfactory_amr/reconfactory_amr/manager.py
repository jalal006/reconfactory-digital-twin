"""Single-robot transport adapter: HTTP/JSON tasks to Nav2 actions."""

from __future__ import annotations

import json
import math
import os
import sys
import time
from collections import deque
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main(args=None):
    import rclpy
    from action_msgs.msg import GoalStatus  # noqa: F401
    from action_msgs.srv import CancelGoal
    from nav2_msgs.action import NavigateToPose
    from nav_msgs.msg import Odometry
    from rclpy.action import ActionClient
    from rclpy.node import Node
    from rclpy.time import Time
    from std_msgs.msg import String
    from tf2_ros import Buffer, TransformException, TransformListener

    class Manager(Node):
        def __init__(self):
            super().__init__("reconfactory_amr_manager")
            self.declare_parameter("project_root", os.getenv("RECONFACTORY_PROJECT_ROOT", ""))
            self.declare_parameter("backend_url", "http://127.0.0.1:8000")
            self.declare_parameter("stations_file", "")
            root = self.get_parameter("project_root").value
            if root:
                sys.path.insert(0, root)
            from reconfactory.transport import load_station_goals

            from .navigation import NavigationRunner

            self.backend = self.get_parameter("backend_url").value.rstrip("/")
            self.stations = load_station_goals(self.get_parameter("stations_file").value)
            self.outbox = deque()
            self.publisher = self.create_publisher(String, "/reconfactory/amr/status", 10)
            self.tasks = self.create_publisher(String, "/reconfactory/amr/task", 10)
            self.client = ActionClient(self, NavigateToPose, "navigate_to_pose")
            self.cancel_orphan = self.create_client(
                CancelGoal, "/navigate_to_pose/_action/cancel_goal"
            )
            self.orphan_cancel_sent = False
            self.orphan_detected = False
            self.session_started = False
            self.stopped_since = None
            self.odom_at = 0.0
            self.runner = NavigationRunner(
                self.stations, self.client, self.goal, self.report, stopped=self.stopped
            )
            self.create_subscription(Odometry, "/odom", self.odometry, 10)
            self.create_subscription(String, "/reconfactory/amr/task", self.receive, 10)
            self.tf = Buffer()
            self.listener = TransformListener(self.tf, self)
            self.create_timer(0.25, self.poll)

        def odometry(self, msg):
            self.odom_at = time.monotonic()
            velocity = msg.twist.twist
            if (
                math.hypot(velocity.linear.x, velocity.linear.y) < 0.03
                and abs(velocity.angular.z) < 0.05
            ):
                if self.stopped_since is None:
                    self.stopped_since = self.odom_at
            else:
                self.stopped_since = None

        def stopped(self):
            now = time.monotonic()
            return (
                self.stopped_since is not None
                and now - self.odom_at < 0.5
                and now - self.stopped_since >= 0.3
            )

        def goal(self, pose):
            goal = NavigateToPose.Goal()
            goal.pose.header.frame_id = "map"
            goal.pose.header.stamp = self.get_clock().now().to_msg()
            goal.pose.pose.position.x = pose["x"]
            goal.pose.pose.position.y = pose["y"]
            goal.pose.pose.orientation.z = math.sin(pose["yaw"] / 2)
            goal.pose.pose.orientation.w = math.cos(pose["yaw"] / 2)
            return goal

        def http(self, path, payload=None):
            data = json.dumps(payload).encode() if payload is not None else None
            request = Request(
                self.backend + path, data=data, headers={"Content-Type": "application/json"}
            )
            with urlopen(request, timeout=0.5) as response:
                return json.load(response)

        def report(self, payload):
            self.publisher.publish(String(data=json.dumps(payload)))
            if self.backend:
                self.outbox.append(payload)
            self.get_logger().info(
                f"{payload['task_id']}: {payload['status']} ({payload['phase']})"
            )

        def receive(self, msg):
            try:
                payload = json.loads(msg.data)
                if payload.get("task_id") in self.runner.registry.seen:
                    return
                # In production only the supervisor can authorize a task.
                if self.backend:
                    state = self.http("/api/transport")
                    active = state.get("active_task") or {}
                    if not state.get("running") or active.get("cancel_requested"):
                        raise ValueError("Transport is paused or cancelled")
                    if any(
                        active.get(k) != payload.get(k)
                        for k in (
                            "task_id",
                            "product_id",
                            "origin",
                            "destination",
                            "payload_loaded",
                            "supersedes_task_id",
                        )
                    ):
                        raise ValueError("Task does not match supervisor authorization")
                self.runner.submit(payload)
            except Exception as exc:
                self.get_logger().warning(f"Transport task refused: {exc}")

        def pose(self):
            try:
                transform = self.tf.lookup_transform("map", "base_link", Time())
                if (
                    self.get_clock().now() - Time.from_msg(transform.header.stamp)
                ).nanoseconds > 2_000_000_000:
                    return None
                p, q = transform.transform.translation, transform.transform.rotation
                return {
                    "x": p.x,
                    "y": p.y,
                    "z": p.z,
                    "yaw": math.atan2(
                        2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z)
                    ),
                }
            except TransformException:
                return None

        def poll(self):
            self.runner.watchdog()
            if (
                self.orphan_detected
                and not self.orphan_cancel_sent
                and self.cancel_orphan.service_is_ready()
            ):
                self.cancel_orphan.call_async(CancelGoal.Request())
                self.orphan_cancel_sent = True
            if not self.backend:
                return
            try:
                state = self.http("/api/transport")
                active = state.get("active_task") or {}
                if not self.session_started:
                    self.session_started = True
                    if active and active.get("status") not in {
                        "delivered",
                        "cancelled",
                        "failed",
                    }:
                        self.runner.uncertain = True
                        self.orphan_detected = True
                task = self.runner.task
                if (
                    task
                    and active.get("task_id") == task.task_id
                    and active.get("cancel_requested")
                ):
                    for key in (
                        "replan_reason",
                        "fault_id",
                        "original_destination",
                        "replan_state",
                    ):
                        setattr(task, key, active.get(key))
                if task and (
                    not state.get("running")
                    or active.get("task_id") != task.task_id
                    or active.get("cancel_requested")
                    or active.get("status") in {"failed", "cancelled"}
                ):
                    self.runner.cancel(
                        invalidate_delivery=(
                            active.get("task_id") == task.task_id
                            and active.get("cancel_requested", False)
                        )
                    )
                # Preserve event order across temporary HTTP failures.
                while self.outbox:
                    try:
                        self.http("/api/transport/status", self.outbox[0])
                    except HTTPError as exc:
                        if exc.code != 409:
                            raise
                        self.get_logger().warning("Supervisor refused stale transport status")
                    self.outbox.popleft()
                pose = self.pose()
                busy = task and task.status not in {"delivered", "failed", "cancelled"}
                self.http(
                    "/api/transport/heartbeat",
                    {
                        "ready": self.client.server_is_ready()
                        and pose is not None
                        and not busy
                        and not self.runner.uncertain,
                        "robot_pose": pose,
                    },
                )
                if (
                    active.get("status") == "requested"
                    and not active.get("cancel_requested")
                    and state.get("running")
                    and not self.runner.uncertain
                ):
                    if active["task_id"] not in self.runner.registry.seen:
                        self.tasks.publish(String(data=json.dumps(active)))
                elif (
                    active
                    and active["task_id"] not in self.runner.registry.seen
                    and active["status"] not in {"delivered", "failed", "cancelled"}
                ):
                    if (
                        active.get("status") == "requested"
                        and active.get("cancel_requested")
                        and not self.runner.uncertain
                    ):
                        # This manager session never submitted the newly authorized
                        # task. No Nav2 goal exists; still require stopped odometry.
                        if self.stopped():
                            self.report(
                                {
                                    **active,
                                    "status": "cancelled",
                                    "failure_reason": "Cancelled before goal submission; robot stopped",
                                }
                            )
                            self.runner.registry.seen.add(active["task_id"])
                        return
                    # Lost goal handles cannot prove cancellation. Request a stop
                    # of this single robot's orphan goal, but never authorize replan.
                    self.runner.uncertain = True
                    self.orphan_detected = True
                    if self.cancel_orphan.service_is_ready() and not self.orphan_cancel_sent:
                        self.cancel_orphan.call_async(CancelGoal.Request())
                        self.orphan_cancel_sent = True
                    self.http(
                        "/api/transport/status",
                        {
                            **active,
                            "status": "failed",
                            "failure_reason": "AMR manager has no goal handle; stop navigation and inspect payload before reset",
                        },
                    )
            except Exception as exc:
                self.runner.cancel()
                self.get_logger().warning(
                    f"AMR backend unavailable: {exc}", throttle_duration_sec=5.0
                )

    rclpy.init(args=args)
    node = Manager()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.runner.cancel()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
