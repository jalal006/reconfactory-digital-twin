"""Check runtime ROS 2 topics for Gazebo camera vision mode."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from collections import Counter

EXPECTED_NODES = {
    "/reconfactory_vision_inspector",
}

EXPECTED_TOPICS = {
    "/reconfactory/vision/image_raw",
    "/reconfactory/vision/result",
    "/reconfactory/vision/debug_image",
}


def _run_ros2(args: list[str]) -> tuple[bool, list[str]]:
    ros2 = shutil.which("ros2")
    if not ros2:
        return False, []
    try:
        completed = subprocess.run(
            [ros2, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, []
    if completed.returncode != 0:
        return False, []
    return True, [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def missing(expected: set[str], actual: set[str]) -> list[str]:
    return sorted(expected - actual)


def sample_images(seconds: float) -> dict[str, object]:
    """Require delivered image bytes; an advertised topic alone is insufficient."""
    result: dict[str, object] = {"valid_images": 0, "sample_seconds": seconds}
    try:
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import Image
    except ImportError as exc:
        return {**result, "error": str(exc)}

    context = rclpy.Context()
    node = None
    executor = None
    try:
        rclpy.init(context=context)
        node = rclpy.create_node("reconfactory_vision_verifier", context=context)
        executor = SingleThreadedExecutor(context=context)
        executor.add_node(node)

        def receive(message: Image) -> None:
            if (
                message.width > 0
                and message.height > 0
                and message.step > 0
                and len(message.data) >= message.step * message.height
            ):
                result["valid_images"] += 1
                result["resolution"] = [message.width, message.height]
                result["encoding"] = message.encoding
                result["frame_id"] = message.header.frame_id

        node.create_subscription(
            Image, "/reconfactory/vision/image_raw", receive, qos_profile_sensor_data
        )
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            executor.spin_once(timeout_sec=max(0.0, min(0.1, deadline - time.monotonic())))
    except Exception as exc:  # noqa: BLE001 - report runtime failures as diagnostics.
        result["error"] = str(exc)
    finally:
        if executor is not None:
            executor.shutdown()
        if node is not None:
            node.destroy_node()
        if context.ok():
            context.shutdown()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-seconds", type=float, default=5.0)
    args = parser.parse_args()
    if not 0 < args.sample_seconds <= 60:
        parser.error("--sample-seconds must be greater than zero and at most 60")
    nodes_ok, nodes = _run_ros2(["node", "list"])
    topics_ok, topics = _run_ros2(["topic", "list"])
    node_set = set(nodes)
    topic_set = set(topics)
    duplicates = sorted(
        node
        for node, count in Counter(nodes).items()
        if count > 1 and node.startswith("/reconfactory_")
    )
    images = sample_images(args.sample_seconds) if topics_ok else {"valid_images": 0}
    result = {
        "ros2_available": nodes_ok and topics_ok,
        "nodes": {node: node in node_set for node in sorted(EXPECTED_NODES)},
        "topics": {topic: topic in topic_set for topic in sorted(EXPECTED_TOPICS)},
        "missing_nodes": missing(EXPECTED_NODES, node_set),
        "missing_topics": missing(EXPECTED_TOPICS, topic_set),
        "duplicate_nodes": duplicates,
        "camera_sample": images,
        "hint": "Run one full stack. Start result echo before spawning a product; results are one-shot.",
        "ok": (
            nodes_ok
            and topics_ok
            and EXPECTED_NODES.issubset(node_set)
            and EXPECTED_TOPICS.issubset(topic_set)
            and not duplicates
            and images["valid_images"] > 0
            and "error" not in images
        ),
    }
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
