"""ROS 2 camera inspection node for the Gazebo vision station."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .http_client import ReConFactoryClient


@dataclass(frozen=True)
class ActiveVisionProduct:
    product_id: str
    product_type: str


@dataclass
class FrameWindow:
    product_id: str | None = None
    started_at: float = 0.0
    inspections: list[tuple[Any, Any]] = field(default_factory=list)
    final_payload: dict[str, Any] | None = None
    submitted: bool = False
    retry_at: float = 0.0

    def reset(self, product_id: str | None = None) -> None:
        self.product_id = product_id
        self.started_at = time.monotonic() if product_id else 0.0
        self.inspections.clear()
        self.final_payload = None
        self.submitted = False
        self.retry_at = 0.0


def configure_project_path(project_root: str | None) -> None:
    if not project_root:
        return
    root = Path(project_root).resolve()
    if root.exists() and str(root) not in sys.path:
        sys.path.insert(0, str(root))


def active_vision_product(snapshot: dict[str, Any]) -> ActiveVisionProduct | None:
    pending = snapshot.get("pending_vision_product_id")
    visual_locations = (snapshot.get("gazebo_visuals") or {}).get("product_locations") or {}
    products = snapshot.get("products", [])
    for product in products:
        product_id = str(product.get("product_id") or "")
        if pending and product_id == pending and visual_locations.get(product_id) == "vision":
            return ActiveVisionProduct(
                product_id=product_id,
                product_type=str(product["product_type"]),
            )
    return None


def recipe_from_snapshot(snapshot: dict[str, Any], product_type: str):
    from reconfactory.models import ProductRecipe

    recipe = snapshot.get("recipes", {}).get(product_type)
    if not isinstance(recipe, dict):
        raise KeyError(f"Recipe not found in backend snapshot: {product_type}")
    return ProductRecipe(
        product_type=str(recipe["product_type"]),
        display_name=str(recipe["display_name"]),
        required_processes=list(recipe["required_processes"]),
        inspection_rule=str(recipe["inspection_rule"]),
        color=str(recipe["color"]),
        shape=str(recipe["shape"]),
    )


def result_payload(
    *,
    product_id: str,
    product_type: str,
    aggregated,
    latency_ms: float,
) -> dict[str, Any]:
    payload = aggregated.to_payload(product_id=product_id, source="gazebo_camera")
    payload["product_type"] = product_type
    payload["inspection_latency_ms"] = round(latency_ms, 2)
    return payload


def main() -> None:
    try:
        import rclpy
        from cv_bridge import CvBridge
        from rclpy.node import Node
        from sensor_msgs.msg import Image
        from std_msgs.msg import String
    except ImportError as exc:
        raise SystemExit(
            "ROS 2 rclpy, sensor_msgs and cv_bridge are required for Gazebo camera vision."
        ) from exc

    class VisionInspectorNode(Node):
        def __init__(self) -> None:
            super().__init__("reconfactory_vision_inspector")
            self.declare_parameter("backend_url", "http://127.0.0.1:8000")
            self.declare_parameter("project_root", os.getenv("RECONFACTORY_PROJECT_ROOT", ""))
            self.declare_parameter("frame_window", 5)
            self.declare_parameter("image_topic", "/reconfactory/vision/image_raw")
            self.declare_parameter("result_topic", "/reconfactory/vision/result")
            self.declare_parameter("debug_image_topic", "/reconfactory/vision/debug_image")
            self.declare_parameter("frame_id", "reconfactory_vision_camera_optical_frame")

            configure_project_path(str(self.get_parameter("project_root").value))
            from vision.opencv_inspector import OpenCVInspector

            self.client = ReConFactoryClient(str(self.get_parameter("backend_url").value))
            self.frame_window = max(1, int(self.get_parameter("frame_window").value))
            self.frame_id = str(self.get_parameter("frame_id").value)
            self.inspector = OpenCVInspector()
            self.bridge = CvBridge()
            self.window = FrameWindow()
            self.last_warning_at = 0.0
            self.result_pub = self.create_publisher(
                String, str(self.get_parameter("result_topic").value), 10
            )
            self.debug_pub = self.create_publisher(
                Image, str(self.get_parameter("debug_image_topic").value), 10
            )
            self.create_subscription(
                Image,
                str(self.get_parameter("image_topic").value),
                self.handle_image,
                10,
            )

        def handle_image(self, message: Image) -> None:
            try:
                snapshot = self.client.status()
                active = active_vision_product(snapshot)
                if active is None:
                    self.window.reset()
                    return
                if self.window.product_id != active.product_id:
                    self.window.reset(active.product_id)
                if self.window.final_payload is not None:
                    self.submit_result()
                    return
                recipe = recipe_from_snapshot(snapshot, active.product_type)
                frame = self.bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
                inspection = self.inspector.inspect_image(
                    frame, recipe, enforce_area=False, enforce_shape=False
                )
                result, features = inspection
                debug = self.inspector.annotate_image(frame, result, features)
                debug_message = self.bridge.cv2_to_imgmsg(debug, encoding="bgr8")
                debug_message.header = message.header
                if not debug_message.header.frame_id:
                    debug_message.header.frame_id = self.frame_id
                self.debug_pub.publish(debug_message)
                if features.area <= 0 or features.dominant_color == "unknown":
                    return
                self.window.inspections.append(inspection)
                if len(self.window.inspections) < self.frame_window:
                    return
                aggregated = self.inspector.aggregate_results(
                    self.window.inspections, recipe, enforce_area=False, enforce_shape=False
                )
                payload = result_payload(
                    product_id=active.product_id,
                    product_type=active.product_type,
                    aggregated=aggregated,
                    latency_ms=(time.monotonic() - self.window.started_at) * 1000.0,
                )
                payload["frame_id"] = message.header.frame_id or self.frame_id
                self.window.final_payload = payload
                ros_message = String()
                ros_message.data = json.dumps(payload)
                self.result_pub.publish(ros_message)
                self.submit_result()
                self.get_logger().info(
                    f"Published Gazebo camera inspection for {active.product_id}: "
                    f"accepted={payload['accepted']} confidence={payload['confidence']}"
                )
            except Exception as exc:  # noqa: BLE001 - keep camera node alive during restarts.
                now = time.monotonic()
                if now - self.last_warning_at >= 5.0:
                    self.get_logger().warning(f"Vision inspection skipped: {exc}")
                    self.last_warning_at = now

        def submit_result(self) -> None:
            if self.window.submitted or time.monotonic() < self.window.retry_at:
                return
            self.window.retry_at = time.monotonic() + 2.0
            self.client.post("/api/vision/result", self.window.final_payload)
            self.window.submitted = True

    rclpy.init()
    node = VisionInspectorNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
