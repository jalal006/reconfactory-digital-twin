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
from uuid import uuid4


def main(args=None):
    import rclpy
    from action_msgs.msg import (
        GoalStatus,  # noqa: F401
        GoalStatusArray,
    )
    from action_msgs.srv import CancelGoal
    from nav2_msgs.action import NavigateToPose
    from nav_msgs.msg import Odometry
    from rclpy.action import ActionClient
    from rclpy.clock import Clock, ClockType
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile
    from rclpy.time import Time
    from sensor_msgs.msg import BatteryState
    from std_msgs.msg import String
    from tf2_ros import Buffer, TransformException, TransformListener

    class Manager(Node):
        def __init__(self):
            super().__init__("reconfactory_amr_manager")
            self.declare_parameter("project_root", os.getenv("RECONFACTORY_PROJECT_ROOT", ""))
            self.declare_parameter("backend_url", "http://127.0.0.1:8000")
            self.declare_parameter("stations_file", "")
            self.declare_parameter("require_safety", True)
            self.require_safety = self.get_parameter("require_safety").value
            if not self.require_safety and not (
                os.getenv("ROS_DOMAIN_ID") == "73"
                and os.getenv("GZ_PARTITION", "").startswith("reconfactory_test_")
            ):
                raise RuntimeError("Ungated manager is restricted to isolated tests")
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
            self.motion = {
                "session_id": uuid4().hex,
                "sequence": 0,
                "elapsed_s": 0.0,
                "distance_m": 0.0,
                "rotation_rad": 0.0,
            }
            self.last_odom_stamp = None
            self.backend_state = None
            self.backend_checked_at = 0.0
            self.lease_sequence = 0
            self.lease_token = None
            self.safety_state = "UNAVAILABLE"
            self.safety_odometry_fresh = False
            self.safety_at = 0.0
            self.nav_status_seen = False
            self.nav_active = True
            self.lease_pub = self.create_publisher(String, "/reconfactory/amr/safety/lease", 1)
            self.create_subscription(
                String,
                "/reconfactory/amr/safety/state",
                self.safety,
                QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL),
            )
            self.create_subscription(
                GoalStatusArray,
                "/navigate_to_pose/_action/status",
                self.nav_status,
                QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL),
            )
            self.battery_publisher = self.create_publisher(
                BatteryState, "/reconfactory/amr/battery_state", 10
            )
            self.runner = NavigationRunner(
                self.stations, self.client, self.goal, self.report, stopped=self.stopped
            )
            self.create_subscription(Odometry, "/odom", self.odometry, 10)
            self.create_subscription(String, "/reconfactory/amr/task", self.receive, 10)
            self.tf = Buffer()
            self.listener = TransformListener(self.tf, self)
            self.create_timer(0.25, self.poll)
            self.create_timer(0.1, self.lease, clock=Clock(clock_type=ClockType.STEADY_TIME))

        def safety(self, msg):
            try:
                state = json.loads(msg.data)
                self.safety_state = state["safety_state"]
                self.safety_odometry_fresh = state.get("odometry_fresh") is True
                self.safety_at = time.monotonic()
            except (KeyError, ValueError, TypeError):
                self.safety_state = "UNAVAILABLE"
                self.safety_odometry_fresh = False

        def nav_status(self, msg):
            self.nav_status_seen = True
            self.nav_active = any(s.status in {1, 2, 3} for s in msg.status_list)

        def safety_available(self):
            return not self.require_safety or (
                self.safety_state in {"DISARMED", "AUTHORIZED", "CONTROLLED_HOLD"}
                and self.safety_odometry_fresh
                and time.monotonic() - self.safety_at < 1.0
            )

        def send_lease(self, mode, token=None, eligible=False, reason=""):
            self.lease_sequence += 1
            task = self.runner.task
            self.lease_pub.publish(
                String(
                    data=json.dumps(
                        {
                            "session_id": self.motion["session_id"],
                            "sequence": self.lease_sequence,
                            "mode": mode,
                            "task_id": token,
                            "mission_type": task.mission_type if task else None,
                            "reset_eligible": eligible,
                            "reason": reason,
                        }
                    )
                )
            )

        def lease(self):
            state = self.backend_state or {}
            active, task = state.get("active_task") or {}, self.runner.task
            fresh = time.monotonic() - self.backend_checked_at < 0.6
            if not fresh:
                self.send_lease(
                    "FAULT_LATCHED" if self.lease_token else "DISARMED",
                    reason="Backend authorization is stale",
                )
                return
            eligible = (
                not state.get("running")
                and not state.get("emergency_active")
                and not active
                and not self.runner.uncertain
                and self.nav_status_seen
                and not self.nav_active
                and self.stopped()
                and (not task or task.status in {"delivered", "failed", "cancelled"})
            )
            authorized = (
                task
                and task.status == "navigating"
                and not task.cancel_requested
                and state.get("running")
                and not state.get("emergency_active")
                and active.get("task_id") == task.task_id
                and not active.get("cancel_requested")
                and active.get("status") not in {"failed", "cancelled", "delivered"}
                and not self.runner.uncertain
                and self.safety_available()
            )
            if authorized:
                token = f"{task.task_id}:{task.phase}:{self.runner.generation}"
                if self.lease_token != token:
                    self.send_lease(
                        "CONTROLLED_HOLD",
                        reason="New navigation generation; discard old commands",
                    )
                    self.lease_token = token
                else:
                    self.send_lease("AUTHORIZED", token)
            else:
                self.send_lease(
                    "DISARMED" if eligible or not active else "CONTROLLED_HOLD",
                    eligible=eligible,
                    reason="Navigation intentionally inhibited",
                )

        def odometry(self, msg):
            if time.monotonic() - self.odom_at >= 0.5:
                self.stopped_since = None
            self.odom_at = time.monotonic()
            velocity = msg.twist.twist
            stamp = msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9
            if self.last_odom_stamp is not None:
                dt = stamp - self.last_odom_stamp
                if 0 < dt <= 1 and all(
                    math.isfinite(v)
                    for v in (velocity.linear.x, velocity.linear.y, velocity.angular.z)
                ):
                    self.motion["sequence"] += 1
                    self.motion["elapsed_s"] += dt
                    self.motion["distance_m"] += (
                        math.hypot(velocity.linear.x, velocity.linear.y) * dt
                    )
                    self.motion["rotation_rad"] += abs(velocity.angular.z) * dt
            self.last_odom_stamp = stamp
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
            self.send_lease("CONTROLLED_HOLD", reason="Navigation phase/status transition")
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
                    if not self.safety_available():
                        raise ValueError("Independent safety gate is latched or unavailable")
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
                            "mission_type",
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
                self.backend_state, self.backend_checked_at = state, time.monotonic()
                active = state.get("active_task") or {}
                if state.get("energy"):
                    from reconfactory.energy import battery_ros_fields

                    battery = BatteryState()
                    battery.header.stamp = self.get_clock().now().to_msg()
                    battery.header.frame_id = "base_link"
                    for key, value in battery_ros_fields(state["energy"]).items():
                        setattr(battery, key, value)
                    self.battery_publisher.publish(battery)
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
                    not active
                    and not state.get("running")
                    and self.nav_status_seen
                    and not self.nav_active
                    and self.stopped()
                    and (not task or task.status in {"delivered", "failed", "cancelled"})
                ):
                    self.runner.uncertain = False
                    self.orphan_detected = False
                    self.orphan_cancel_sent = False
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
                    not self.safety_available()
                    or not state.get("running")
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
                        and self.safety_available()
                        and not self.runner.uncertain,
                        "robot_pose": pose,
                        "motion": self.motion,
                    },
                )
                if (
                    active.get("status") == "requested"
                    and not active.get("cancel_requested")
                    and state.get("running")
                    and not self.runner.uncertain
                    and self.safety_available()
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
                self.backend_checked_at = 0.0
                self.send_lease(
                    "FAULT_LATCHED" if self.lease_token else "DISARMED",
                    reason="Backend communication failed",
                )
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
