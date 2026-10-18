"""Independent velocity gate. HTTP reporting never executes in the control callback."""

import json
import math
import os
import sys
import threading
from collections import deque
from urllib.request import Request, urlopen


def main(args=None):
    import rclpy
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    from rclpy.clock import Clock, ClockType
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile
    from std_msgs.msg import String
    from std_srvs.srv import Trigger

    class SafetyNode(Node):
        def __init__(self):
            super().__init__("reconfactory_amr_safety")
            self.declare_parameter("project_root", os.getenv("RECONFACTORY_PROJECT_ROOT", ""))
            self.declare_parameter("backend_url", "http://127.0.0.1:8000")
            sys.path.insert(0, self.get_parameter("project_root").value)
            from reconfactory.amr_safety import MotionSafety, SafetyConfig

            defaults = SafetyConfig()
            parameters = {}
            for name, value in vars(defaults).items():
                self.declare_parameter(name, value)
                parameters[name] = self.get_parameter(name).value
            self.policy = MotionSafety(SafetyConfig(**parameters))
            self.output = self.create_publisher(Twist, "/cmd_vel", 1)
            self.state_pub = self.create_publisher(
                String,
                "/reconfactory/amr/safety/state",
                QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL),
            )
            self.create_subscription(Twist, "/reconfactory/amr/nav_cmd_vel", self.command, 1)
            self.create_subscription(String, "/reconfactory/amr/safety/lease", self.lease, 1)
            self.create_subscription(Odometry, "/odom", self.odom, 1)
            self.create_service(Trigger, "/reconfactory/amr/safety/reset", self.reset)
            self.queue = deque(maxlen=1024)
            self.latest = {}
            self.shutdown_event = threading.Event()
            self.worker = threading.Thread(target=self.report, daemon=True)
            self.worker.start()
            self.create_timer(0.05, self.tick, clock=Clock(clock_type=ClockType.STEADY_TIME))

        def command(self, msg):
            self.policy.velocity(
                (
                    msg.linear.x,
                    msg.linear.y,
                    msg.linear.z,
                    msg.angular.x,
                    msg.angular.y,
                    msg.angular.z,
                )
            )

        def lease(self, msg):
            try:
                self.policy.lease(json.loads(msg.data))
            except (ValueError, TypeError):
                self.policy.fault("Malformed lease JSON")

        def odom(self, msg):
            v = msg.twist.twist
            self.policy.odometry(math.hypot(v.linear.x, v.linear.y), v.angular.z)

        def reset(self, request, response):
            response.success, response.message = self.policy.reset()
            return response

        def tick(self):
            values = self.policy.tick()
            msg = Twist()
            msg.linear.x, msg.linear.y, msg.linear.z = values[:3]
            msg.angular.x, msg.angular.y, msg.angular.z = values[3:]
            self.output.publish(msg)
            self.latest = self.policy.snapshot()
            self.state_pub.publish(String(data=json.dumps(self.latest)))
            while self.policy.events:
                self.queue.append(self.policy.events.popleft())

        def report(self):
            url = self.get_parameter("backend_url").value.rstrip("/") + "/api/transport/safety"
            pending = None
            while not self.shutdown_event.wait(0.25):
                if not self.latest:
                    continue
                if pending is None and self.queue:
                    pending = self.queue.popleft()
                try:
                    data = {"state": self.latest, "events": [pending] if pending else []}
                    request = Request(
                        url,
                        data=json.dumps(data).encode(),
                        headers={"Content-Type": "application/json"},
                    )
                    with urlopen(request, timeout=0.5) as response:
                        response.read()
                    pending = None
                except Exception:
                    pass  # Observation loss never blocks the zero-command loop.

    rclpy.init(args=args)
    node = SafetyNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.output.publish(Twist())
        node.shutdown_event.set()
        node.worker.join(timeout=1)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
