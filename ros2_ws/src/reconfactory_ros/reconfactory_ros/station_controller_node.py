"""ROS 2 command node for station recovery and fault injection."""

from __future__ import annotations

import json
from typing import Any

from .http_client import ReConFactoryClient


def dispatch_command(client: ReConFactoryClient, payload: dict[str, Any]) -> dict[str, Any]:
    """Translate one ROS command message into a backend API operation."""
    command = str(payload.get("command", "")).strip().lower()
    if command == "start":
        return client.post("/api/start")
    if command in {"pause", "stop"}:
        return client.post("/api/stop")
    if command == "reset":
        return client.post("/api/reset")
    if command == "emergency_stop":
        return client.post("/api/emergency-stop")
    if command == "add_product":
        return client.post(
            "/api/products",
            {
                "product_type": payload["product_type"],
                "defect_flags": payload.get("defect_flags", []),
            },
        )
    if command == "recover":
        return client.post("/api/recover", {"machine_id": payload["machine_id"]})
    if command == "fault":
        return client.post(
            "/api/faults",
            {
                "machine_id": payload["machine_id"],
                "fault_type": payload["fault_type"],
                "reason": payload.get("reason", "ROS 2 command"),
            },
        )
    raise ValueError(f"Unsupported ROS 2 command: {command or '<empty>'}")


def main() -> None:
    try:
        import rclpy
        from rclpy.node import Node
        from std_msgs.msg import String
    except ImportError as exc:
        raise SystemExit("ROS 2 rclpy is required. Run this inside a ROS 2 workspace.") from exc

    class StationControllerNode(Node):
        def __init__(self) -> None:
            super().__init__("reconfactory_station_controller_node")
            self.declare_parameter("backend_url", "http://127.0.0.1:8000")
            backend_url = self.get_parameter("backend_url").value
            self.client = ReConFactoryClient(backend_url)
            self.create_subscription(
                String,
                "reconfactory/station_command",
                self.handle_command,
                10,
            )
            self.create_subscription(
                String,
                "reconfactory/factory_command",
                self.handle_command,
                10,
            )

        def handle_command(self, message: String) -> None:
            try:
                payload = json.loads(message.data)
                if not isinstance(payload, dict):
                    raise ValueError("Command payload must be a JSON object.")
                dispatch_command(self.client, payload)
            except (KeyError, TypeError, ValueError, OSError) as exc:
                self.get_logger().error(f"ROS command rejected: {exc}")

    rclpy.init()
    node = StationControllerNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
