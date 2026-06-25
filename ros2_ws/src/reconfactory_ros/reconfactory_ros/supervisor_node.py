"""Publishes factory snapshots from the FastAPI backend to ROS 2."""

from __future__ import annotations

import json

from .http_client import ReConFactoryClient


def main() -> None:
    try:
        import rclpy
        from rclpy.node import Node
        from std_msgs.msg import String
    except ImportError as exc:
        raise SystemExit("ROS 2 rclpy is required. Run this inside a ROS 2 workspace.") from exc

    class SupervisorNode(Node):
        def __init__(self) -> None:
            super().__init__("reconfactory_supervisor_node")
            self.declare_parameter("backend_url", "http://127.0.0.1:8000")
            backend_url = self.get_parameter("backend_url").value
            self.client = ReConFactoryClient(backend_url)
            self.publisher = self.create_publisher(String, "reconfactory/factory_state", 10)
            self.timer = self.create_timer(0.5, self.publish_state)

        def publish_state(self) -> None:
            message = String()
            try:
                message.data = json.dumps(self.client.status())
                self.publisher.publish(message)
            except Exception as exc:  # noqa: BLE001 - keep bridge alive during backend restarts.
                self.get_logger().warning(f"Backend unavailable: {exc}")

    rclpy.init()
    node = SupervisorNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
