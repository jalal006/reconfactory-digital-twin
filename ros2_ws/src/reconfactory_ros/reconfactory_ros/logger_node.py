"""ROS 2 node that logs factory events to the ROS logger."""

from __future__ import annotations

import json


def main() -> None:
    try:
        import rclpy
        from rclpy.node import Node
        from std_msgs.msg import String
    except ImportError as exc:
        raise SystemExit("ROS 2 rclpy is required. Run this inside a ROS 2 workspace.") from exc

    class LoggerNode(Node):
        def __init__(self) -> None:
            super().__init__("reconfactory_logger_node")
            self.create_subscription(
                String,
                "reconfactory/factory_state",
                self.log_state_summary,
                10,
            )

        def log_state_summary(self, message: String) -> None:
            snapshot = json.loads(message.data)
            stats = snapshot["stats"]
            self.get_logger().info(
                f"tick={snapshot['tick']} "
                f"completed={stats['completed_products']} "
                f"faults={stats['fault_count']} "
                f"rerouted={stats['rerouted_products']}"
            )

    rclpy.init()
    node = LoggerNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
