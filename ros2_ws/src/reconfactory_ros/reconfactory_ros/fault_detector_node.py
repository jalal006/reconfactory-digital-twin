"""Publishes ReConFactory fault records as ROS 2 messages."""

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

    class FaultDetectorNode(Node):
        def __init__(self) -> None:
            super().__init__("reconfactory_fault_detector_node")
            self.declare_parameter("backend_url", "http://127.0.0.1:8000")
            backend_url = self.get_parameter("backend_url").value
            self.client = ReConFactoryClient(backend_url)
            self.publisher = self.create_publisher(String, "reconfactory/faults", 10)
            self.seen_faults: set[str] = set()
            self.timer = self.create_timer(0.5, self.publish_faults)

        def publish_faults(self) -> None:
            try:
                snapshot = self.client.status()
            except Exception as exc:  # noqa: BLE001
                self.get_logger().warning(f"Backend unavailable: {exc}")
                return
            for fault in snapshot.get("faults", []):
                if fault["fault_id"] in self.seen_faults:
                    continue
                self.seen_faults.add(fault["fault_id"])
                message = String()
                message.data = json.dumps(fault)
                self.publisher.publish(message)

    rclpy.init()
    node = FaultDetectorNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
