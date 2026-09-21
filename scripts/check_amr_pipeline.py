"""Bounded live ROS checks, with optional real navigation (never teleports the robot)."""

from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@dataclass
class MotionTrace:
    distance: float = 0.0
    rotation: float = 0.0
    last: tuple[float, float, float, float] | None = None

    def update(self, stamp: float, x: float, y: float, yaw: float) -> None:
        if not all(math.isfinite(v) for v in (stamp, x, y, yaw)):
            return
        if self.last is not None:
            t, px, py, previous_yaw = self.last
            if stamp <= t:
                return
            self.distance += math.hypot(x - px, y - py)
            delta = yaw - previous_yaw
            self.rotation += abs(math.atan2(math.sin(delta), math.cos(delta)))
        self.last = (stamp, x, y, yaw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goals", nargs="*", default=[])
    parser.add_argument(
        "--plan-all",
        action="store_true",
        help="Check all named station pairs with the real Nav2 planner before moving",
    )
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--max-turn-radians", type=float, default=2 * math.pi)
    parser.add_argument(
        "--manual-drive", action="store_true", help="Use only with enable_nav2:=false"
    )
    args = parser.parse_args()
    import rclpy
    from geometry_msgs.msg import Twist
    from nav2_msgs.action import ComputePathToPose, NavigateToPose
    from nav_msgs.msg import Odometry
    from rclpy.action import ActionClient
    from rclpy.parameter import Parameter
    from rclpy.qos import qos_profile_sensor_data
    from rclpy.time import Time
    from sensor_msgs.msg import LaserScan
    from tf2_ros import Buffer, TransformException, TransformListener

    from reconfactory.transport import load_station_goals

    stations = load_station_goals(ROOT / "ros2_ws/src/reconfactory_amr/config/stations.yaml")
    nav_config = yaml.safe_load(
        (ROOT / "ros2_ws/src/reconfactory_amr/config/nav2.yaml").read_text()
    )
    goal_limits = nav_config["controller_server"]["ros__parameters"]["goal_checker"]
    rclpy.init()
    node = rclpy.create_node(
        "reconfactory_amr_verifier", parameter_overrides=[Parameter("use_sim_time", value=True)]
    )
    samples = {}
    motion = MotionTrace()

    def odometry(msg):
        samples["odom"] = msg
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        motion.update(
            msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9,
            p.x,
            p.y,
            math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z)),
        )

    node.create_subscription(
        LaserScan, "/scan", lambda msg: samples.update(scan=msg), qos_profile_sensor_data
    )
    node.create_subscription(Odometry, "/odom", odometry, qos_profile_sensor_data)
    node.create_subscription(Twist, "/cmd_vel", lambda msg: samples.update(command=msg), 10)
    node.create_subscription(
        Twist, "/cmd_vel_nav", lambda msg: samples.update(raw_command=msg), 10
    )
    buffer = Buffer()
    listener = TransformListener(buffer, node)
    client = ActionClient(node, NavigateToPose, "/navigate_to_pose")

    def report_pose():
        try:
            transform = buffer.lookup_transform("map", "base_link", Time()).transform
            p, q = transform.translation, transform.rotation
            yaw = math.atan2(2 * q.w * q.z, 1 - 2 * q.z * q.z)
            command = samples.get("command", Twist())
            raw = samples.get("raw_command", Twist())
            measured = samples["odom"].twist.twist
            print(
                f"Navigation pose=({p.x:.2f}, {p.y:.2f}, yaw={yaw:.2f}) "
                f"cmd=({command.linear.x:.3f} m/s, {command.angular.z:.3f} rad/s) "
                f"raw_w={raw.angular.z:.3f} odom_w={measured.angular.z:.3f} "
                f"total_turn={math.degrees(motion.rotation):.0f} deg",
                flush=True,
            )
        except TransformException:
            print("Navigation pose unavailable", flush=True)

    def wait(predicate, timeout):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            rclpy.spin_once(node, timeout_sec=0.1)
            if predicate():
                return True
        return False

    def transform_ready():
        try:
            buffer.lookup_transform(
                "odom" if args.manual_drive else "map", "laser_link", Time()
            )
            return True
        except TransformException:
            return False

    try:
        assert wait(
            lambda: "scan" in samples and "odom" in samples and transform_ready(), args.timeout
        ), "Timed out waiting for scan, odometry and TF"
        assert any(math.isfinite(r) and r > 0 for r in samples["scan"].ranges), (
            "No finite LiDAR returns"
        )
        print("PASS: live LiDAR, odometry and TF", flush=True)
        if args.manual_drive:
            pub = node.create_publisher(Twist, "/cmd_vel", 10)
            before = samples["odom"].pose.pose.position
            command = Twist()
            command.linear.x = 0.1
            try:
                for _ in range(30):
                    pub.publish(command)
                    rclpy.spin_once(node, timeout_sec=0.1)
                    time.sleep(0.05)
            finally:
                pub.publish(Twist())
            after = samples["odom"].pose.pose.position
            assert math.hypot(after.x - before.x, after.y - before.y) > 0.03, (
                "cmd_vel did not move robot"
            )
            print("PASS: manual cmd_vel changed odometry", flush=True)
            before = samples["odom"].pose.pose.orientation
            command = Twist()
            command.angular.z = 0.4
            try:
                for _ in range(40):
                    pub.publish(command)
                    rclpy.spin_once(node, timeout_sec=0.1)
                    time.sleep(0.05)
            finally:
                pub.publish(Twist())
            after = samples["odom"].pose.pose.orientation
            yaw_delta = 2 * math.atan2(
                after.z * before.w - after.w * before.z,
                after.w * before.w + after.z * before.z,
            )
            assert abs(yaw_delta) > 0.1, "cmd_vel did not turn robot"
            print("PASS: manual angular cmd_vel changed yaw", flush=True)
        else:
            assert wait(client.server_is_ready, args.timeout), "NavigateToPose unavailable"
            print("PASS: NavigateToPose action server", flush=True)
        if args.plan_all:
            planner = ActionClient(node, ComputePathToPose, "/compute_path_to_pose")
            assert wait(planner.server_is_ready, args.timeout), "Planner action unavailable"

            def stamped(pose):
                goal = NavigateToPose.Goal()
                goal.pose.header.frame_id = "map"
                goal.pose.header.stamp = node.get_clock().now().to_msg()
                goal.pose.pose.position.x, goal.pose.pose.position.y = pose["x"], pose["y"]
                goal.pose.pose.orientation.z = math.sin(pose["yaw"] / 2)
                goal.pose.pose.orientation.w = math.cos(pose["yaw"] / 2)
                return goal.pose

            for origin, start in stations.items():
                for destination, end in stations.items():
                    if origin == destination:
                        continue
                    goal = ComputePathToPose.Goal()
                    goal.start, goal.goal = stamped(start), stamped(end)
                    goal.use_start = True
                    goal.planner_id = "GridBased"
                    response = planner.send_goal_async(goal)
                    assert wait(response.done, 10), "Planner goal response timeout"
                    assert response.result().accepted, "Planner rejected request"
                    result = response.result().get_result_async()
                    assert wait(result.done, 10), "Planner result timeout"
                    assert result.result().status == 4 and result.result().result.path.poses, (
                        f"No Nav2 path: {origin} -> {destination}"
                    )
                    if origin in {
                        "vision",
                        "station_a",
                        "station_b",
                        "quality",
                    } and destination in {
                        "station_a",
                        "station_b",
                        "quality",
                        "accepted_output",
                        "reject_output",
                    }:
                        poses = result.result().result.path.poses
                        length = sum(
                            math.hypot(
                                b.pose.position.x - a.pose.position.x,
                                b.pose.position.y - a.pose.position.y,
                            )
                            for a, b in zip(poses, poses[1:], strict=False)
                        )
                        direct = math.hypot(end["x"] - start["x"], end["y"] - start["y"])
                        assert length <= 1.6 * direct + 0.5, (
                            f"Unexpected factory detour: {origin} -> {destination}: {length:.2f} m"
                        )
                        print(
                            f"Path {origin} -> {destination}: {length:.2f} m (direct {direct:.2f} m)",
                            flush=True,
                        )
            print(
                "PASS: Nav2 planned all 56 directed station pairs (planning only)", flush=True
            )
        for name in args.goals:
            motion = MotionTrace()
            goal_started = time.monotonic()
            p = stations[name]
            goal = NavigateToPose.Goal()
            goal.pose.header.frame_id = "map"
            goal.pose.header.stamp = node.get_clock().now().to_msg()
            goal.pose.pose.position.x, goal.pose.pose.position.y = p["x"], p["y"]
            goal.pose.pose.orientation.z = math.sin(p["yaw"] / 2)
            goal.pose.pose.orientation.w = math.cos(p["yaw"] / 2)
            response = client.send_goal_async(goal)
            assert wait(response.done, 10), "Nav2 did not acknowledge goal"
            handle = response.result()
            assert handle.accepted, f"Goal {name} rejected"
            result = handle.get_result_async()
            deadline = time.monotonic() + args.timeout
            while not result.done() and time.monotonic() < deadline:
                wait(result.done, min(10, max(0, deadline - time.monotonic())))
                report_pose()
            if not result.done():
                handle.cancel_goal_async()
                raise RuntimeError(f"Goal {name} timed out (cancel requested)")
            assert result.result().status == 4, (
                f"Goal {name} failed: action status {result.result().status}"
            )
            actual = buffer.lookup_transform("map", "base_link", Time()).transform.translation
            error = math.hypot(actual.x - p["x"], actual.y - p["y"])
            assert error <= goal_limits["xy_goal_tolerance"] + 0.05, (
                f"Goal reported success but map pose error is {error:.2f} m"
            )
            velocity = samples["odom"].twist.twist
            linear = math.hypot(velocity.linear.x, velocity.linear.y)
            angular = abs(velocity.angular.z)
            assert linear <= goal_limits["trans_stopped_velocity"] + 0.02, (
                "Arrived while moving"
            )
            assert angular <= goal_limits["rot_stopped_velocity"] + 0.02, (
                "Arrived while rotating"
            )
            assert motion.rotation <= args.max_turn_radians, (
                f"Excessive turning to {name}: {math.degrees(motion.rotation):.0f} degrees"
            )
            print(
                f"PASS: {name}, actual map pose ({actual.x:.2f}, {actual.y:.2f}), "
                f"error {error:.2f} m, {time.monotonic() - goal_started:.1f} s, "
                f"arrival speed {linear:.3f} m/s / {angular:.3f} rad/s, "
                f"distance {motion.distance:.2f} m, turn {math.degrees(motion.rotation):.0f} deg",
                flush=True,
            )
    finally:
        del listener
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
