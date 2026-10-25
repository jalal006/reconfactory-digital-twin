"""Gazebo watchdog observation and operator recovery; never publishes velocity."""

import json
import os
import subprocess
import sys
import threading
import time
from urllib.request import Request, urlopen


def main(args=None):
    import rclpy
    from action_msgs.msg import GoalStatusArray
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile
    from std_msgs.msg import String
    from std_srvs.srv import Trigger

    class Observer(Node):
        def __init__(self):
            super().__init__("reconfactory_actuator_observer")
            self.declare_parameter("project_root", os.getenv("RECONFACTORY_PROJECT_ROOT", ""))
            self.declare_parameter("backend_url", "http://127.0.0.1:8000")
            sys.path.insert(0, self.get_parameter("project_root").value)
            self.url = self.get_parameter("backend_url").value.rstrip("/")
            self.data, self.at = {}, {}
            self.nav_idle = False
            self.odom_at, self.stopped_since = 0.0, None
            latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
            for key, topic, qos in (
                ("watchdog", "/reconfactory/amr/actuator/state", 1),
                ("gate", "/reconfactory/amr/safety/state", latched),
                ("lease", "/reconfactory/amr/safety/lease", 1),
            ):
                self.create_subscription(
                    String, topic, lambda msg, k=key: self.observe(k, msg), qos
                )
            self.create_subscription(
                GoalStatusArray, "/navigate_to_pose/_action/status", self.goals, latched
            )
            self.create_subscription(Odometry, "/odom", self.odom, 1)
            self.create_service(Trigger, "/reconfactory/amr/actuator/reset", self.reset)
            self.stop = threading.Event()
            self.worker = threading.Thread(target=self.report, daemon=True)
            self.worker.start()

        def observe(self, key, msg):
            from reconfactory.actuator_watchdog import validate_observation

            try:
                value = json.loads(msg.data)
                if not isinstance(value, dict):
                    return
                if key == "watchdog":
                    validate_observation(value)
                    old = self.data.get(key, {})
                    if value["instance_id"] == old.get("instance_id") and value[
                        "sample_sequence"
                    ] <= old.get("sample_sequence", 0):
                        return
                self.data[key], self.at[key] = value, time.monotonic()
            except (ValueError, TypeError):
                self.at[key] = 0

        def goals(self, msg):
            self.nav_idle = not any(s.status in {1, 2, 3} for s in msg.status_list)
            self.at["goals"] = time.monotonic()

        def odom(self, msg):
            import math

            now = time.monotonic()
            v = msg.twist.twist
            if now - self.odom_at >= 0.5 or not (
                math.hypot(v.linear.x, v.linear.y) < 0.03 and abs(v.angular.z) < 0.05
            ):
                self.stopped_since = None
            elif self.stopped_since is None:
                self.stopped_since = now
            self.odom_at = now

        def report(self):
            while not self.stop.wait(0.25):
                if time.monotonic() - self.at.get("watchdog", 0) >= 0.5:
                    continue
                try:
                    req = Request(
                        self.url + "/api/transport/actuator",
                        data=json.dumps({"state": self.data["watchdog"]}).encode(),
                        headers={"Content-Type": "application/json"},
                    )
                    with urlopen(req, timeout=0.5) as response:
                        response.read()
                except Exception:
                    pass  # Observation is never part of actuator control.

        def reset(self, request, response):
            from reconfactory.actuator_watchdog import recovery_allowed

            response.success = False
            response.message = "Require reconciled idle backend/manager, DISARMED ROS gate, and fresh stopped odometry"
            try:
                with urlopen(self.url + "/api/transport", timeout=0.5) as reply:
                    backend = json.load(reply)
                now = time.monotonic()
                allowed = recovery_allowed(
                    backend,
                    self.data.get("gate", {}),
                    self.data.get("lease", {}),
                    self.data.get("watchdog", {}),
                    observations_fresh=all(
                        now - self.at.get(k, 0) < 0.5 for k in ("gate", "lease", "watchdog")
                    ),
                    nav_idle=self.nav_idle and "goals" in self.at,
                    stopped=now - self.odom_at < 0.5
                    and self.stopped_since is not None
                    and now - self.stopped_since >= 0.3,
                )
                if not allowed:
                    return response
                result = subprocess.run(
                    [
                        "gz",
                        "service",
                        "-s",
                        "/amr/actuator_watchdog/reset",
                        "--reqtype",
                        "gz.msgs.Boolean",
                        "--reptype",
                        "gz.msgs.Boolean",
                        "--timeout",
                        "1500",
                        "--req",
                        "data: true",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                response.success = (
                    result.returncode == 0 and result.stdout.strip() == "data: true"
                )
                response.message = (
                    "Reset accepted; fresh zero startup required"
                    if response.success
                    else "Gazebo reset rejected or unavailable"
                )
            except Exception as exc:
                response.message = f"Recovery unavailable: {exc}"
            return response

    rclpy.init(args=args)
    node = Observer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop.set()
        node.worker.join(timeout=1)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
