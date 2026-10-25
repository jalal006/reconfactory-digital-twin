"""Real isolated failure injection. Never signals processes outside the test launcher."""

import argparse
import json
import math
import os
import signal
import subprocess
import time
from pathlib import Path
from urllib.request import Request, urlopen

from check_amr_resilience import owned_process

ROOT = Path(__file__).resolve().parents[1]


def recovery_action(samples, now):
    """Next step of the test's explicit recovery, based on both observed layers."""
    if not all(
        0 <= now - samples.get(key, -math.inf) < 0.5
        for key in ("safety_at", "actuator_at", "odom_at")
    ) or not (
        samples.get("speed", math.inf) < 0.03 and samples.get("angular", math.inf) < 0.05
    ):
        return None
    gate = samples.get("safety", {}).get("safety_state")
    actuator = samples.get("actuator", {})
    if gate == "FAULT_LATCHED":
        return "reset_gate"
    if gate != "DISARMED":
        return None
    if actuator.get("state") == "FAULT_LATCHED":
        return "reset_actuator"
    if actuator.get("state") == "ARMED" or (
        actuator.get("state") == "STARTUP_INHIBITED" and actuator.get("startup_ready") is True
    ):
        return "ready"
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--group", required=True, type=int)
    parser.add_argument(
        "--scenario", choices=["manager-crash", "backend-outage", "gate-crash"], required=True
    )
    args = parser.parse_args()
    import rclpy
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    from rclpy.qos import DurabilityPolicy, QoSProfile
    from std_msgs.msg import String
    from std_srvs.srv import Trigger

    def http(path, payload=None):
        req = Request(
            args.url + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=1) as response:
            return json.load(response)

    rclpy.init()
    node = rclpy.create_node("reconfactory_safety_verifier")
    samples = {}
    trace = []

    def odom(msg):
        v = msg.twist.twist
        position = (msg.pose.pose.position.x, msg.pose.pose.position.y)
        if "position" in samples:
            samples["distance"] = samples.get("distance", 0) + math.dist(
                position, samples["position"]
            )
        samples.update(
            odom_at=time.monotonic(),
            speed=math.hypot(v.linear.x, v.linear.y),
            angular=abs(v.angular.z),
            position=position,
        )

    def command(msg):
        samples.update(cmd_at=time.monotonic(), command=math.hypot(msg.linear.x, msg.angular.z))

    def safety(msg):
        samples.update(safety=json.loads(msg.data), safety_at=time.monotonic())

    node.create_subscription(Odometry, "/odom", odom, 1)
    node.create_subscription(Twist, "/cmd_vel", command, 1)
    node.create_subscription(
        Twist,
        "/reconfactory/amr/actuator/command",
        lambda msg: samples.update(
            actuator_cmd_at=time.monotonic(),
            actuator_command=math.hypot(msg.linear.x, msg.angular.z),
        ),
        1,
    )
    node.create_subscription(
        String,
        "/reconfactory/amr/actuator/state",
        lambda msg: samples.update(actuator=json.loads(msg.data), actuator_at=time.monotonic()),
        1,
    )
    node.create_subscription(
        String,
        "/reconfactory/amr/safety/state",
        safety,
        QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL),
    )
    reset = node.create_client(Trigger, "/reconfactory/amr/safety/reset")
    actuator_reset = node.create_client(Trigger, "/reconfactory/amr/actuator/reset")

    def spin():
        for _ in range(8):
            rclpy.spin_once(node, timeout_sec=0.01)

    def reset_result(client=reset):
        assert client.wait_for_service(timeout_sec=2)
        future = client.call_async(Trigger.Request())
        deadline = time.monotonic() + 3
        while not future.done() and time.monotonic() < deadline:
            spin()
        assert future.done(), "Reset service timeout"
        return future.result().success

    replacement, suspended, logfile = None, None, None
    result = {"scenario": args.scenario, "certified_safety": False}
    try:
        topology = {}
        for topic in ("/amr/cmd_vel_requested", "/amr/actuator_cmd_vel"):
            info = subprocess.run(
                ["gz", "topic", "-i", "-t", topic], capture_output=True, text=True, timeout=5
            )
            assert info.returncode == 0, info.stderr
            topology[topic] = info.stdout
            publishers = info.stdout.split("Subscribers")[0].splitlines()[1:]
            assert len(publishers) == 1 and "gz.msgs.Twist" in publishers[0], info.stdout
        requested_publisher = topology["/amr/cmd_vel_requested"].splitlines()[1]
        actuator_publisher = topology["/amr/actuator_cmd_vel"].splitlines()[1]
        assert requested_publisher != actuator_publisher, (
            "Bridge must not publish actuator commands"
        )
        assert (
            actuator_publisher.strip()
            in topology["/amr/cmd_vel_requested"].split("Subscribers")[1]
        )
        result["gazebo_topic_topology"] = topology
        product = http("/api/products", {"product_type": "red_block"})["product"]
        http("/api/start", {})
        deadline = time.monotonic() + 100
        while time.monotonic() < deadline:
            spin()
            state = http("/api/status")
            task = state["transport"].get("active_task") or {}
            pose = state["transport"].get("robot_pose") or {}
            if (
                task.get("destination") == "station_a"
                and task.get("phase") == "delivery"
                and task.get("status") == "navigating"
                and 0.40 < samples.get("speed", 0) < 0.5
                and 2.4 < pose.get("x", 0) < 3.5
                and samples.get("command", 0) > 0.1
                and samples.get("safety", {}).get("safety_state") == "AUTHORIZED"
                and samples.get("actuator", {}).get("state") == "ARMED"
            ):
                break
        else:
            raise AssertionError(f"Loaded moving robot not observed: {state['transport']}")
        publishers = node.get_publishers_info_by_topic("/cmd_vel")
        assert [p.node_name for p in publishers] == ["reconfactory_amr_safety"], publishers
        result.update(
            initial_speed=samples["speed"],
            initial_pose=pose,
            task_id=task["task_id"],
            sole_cmd_vel_publisher=publishers[0].node_name,
        )
        assert not reset_result(), "Reset during active navigation should be denied"
        assert not reset_result(actuator_reset), (
            "Actuator reset during navigation should be denied"
        )
        marker = {
            "manager-crash": "/amr_manager",
            "gate-crash": "/safety_supervisor",
            "backend-outage": "scripts/run_factory.py",
        }[args.scenario]
        pid, argv, env = owned_process(args.group, marker)
        start = time.monotonic()
        initial_distance = samples.get("distance", 0)
        last_ros_command_at = samples.get("cmd_at")
        os.kill(pid, signal.SIGSTOP if args.scenario == "backend-outage" else signal.SIGKILL)
        if args.scenario == "backend-outage":
            suspended = pid
        inhibit, stop, stable, fault_at = None, None, None, None
        deadline = start + 8
        while time.monotonic() < deadline:
            spin()
            now = time.monotonic()
            s = samples.get("safety", {})
            gate_crash = args.scenario == "gate-crash"
            cmd_at = samples.get("actuator_cmd_at" if gate_crash else "cmd_at", 0)
            cmd = samples.get("actuator_command" if gate_crash else "command", 1)
            if cmd_at > start and cmd < 1e-8:
                inhibit = inhibit or now
            fault = samples.get("actuator", {}) if gate_crash else s
            state_key = "state" if gate_crash else "safety_state"
            if (
                samples.get("actuator_at" if gate_crash else "safety_at", 0) > start
                and fault.get(state_key) == "FAULT_LATCHED"
            ):
                if fault_at is None:
                    result["fault_reason"] = fault.get(
                        "reason" if gate_crash else "safety_reason"
                    )
                    result["heartbeat_age_at_latch_ms"] = s.get("heartbeat_age_ms")
                fault_at = fault_at or now
            if (
                now - samples.get("odom_at", 0) < 0.5
                and samples.get("speed", 1) < 0.03
                and samples.get("angular", 1) < 0.05
            ):
                stable = stable or now
                if now - stable >= 0.3:
                    if stop is None:
                        result["stop_distance_m"] = (
                            samples.get("distance", 0) - initial_distance
                        )
                        stop = now
            else:
                stable = None
                if stop:
                    raise AssertionError("Movement resumed without reset")
            trace.append(
                {
                    "elapsed_s": now - start,
                    "speed": samples.get("speed"),
                    "angular": samples.get("angular"),
                    "command": samples.get("command"),
                    "safety_state": s.get("safety_state"),
                    "actuator_state": samples.get("actuator", {}).get("state"),
                    "actuator_command": samples.get("actuator_command"),
                    "travel_distance_m": samples.get("distance", 0) - initial_distance,
                }
            )
            if stop and now - stop >= 2:
                break
        result.update(
            command_inhibition_s=inhibit - start if inhibit else None,
            physical_stop_s=stop - start if stop else None,
            fault_latch_s=fault_at - start if fault_at else None,
            manager_restart_required_for_stop=False,
            trace=trace,
            last_ros_command_before_signal_s=start - last_ros_command_at,
            command_age_at_timeout_ms=samples.get("actuator", {}).get(
                "command_age_at_timeout_ms"
            ),
            cleanup_publisher_used=False,
        )
        assert inhibit and stop and fault_at, result
        if args.scenario == "gate-crash":
            assert result["fault_reason"] == "Command stream timeout", result
            assert samples["cmd_at"] - start < 0.3, "ROS stream unexpectedly continued"
            result["gate_failure_bounded_stop_verified"] = True
            result["one_point_five_second_target_met"] = stop - start <= 1.5
            before_reset = samples["actuator"]["transition_sequence"]
            invalid = subprocess.run(
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
            # Protobuf text omits the default false field; also require a new
            # rejection event so an empty CLI output cannot hide a missing service.
            assert invalid.returncode == 0 and invalid.stdout.strip() in {"", "data: false"}, (
                invalid
            )
            until = time.monotonic() + 2
            while time.monotonic() < until:
                spin()
                if samples["actuator"]["transition_sequence"] > before_reset:
                    break
            assert samples["actuator"]["transition_sequence"] > before_reset
            assert (
                samples["actuator"]["events"][-1]["event_type"]
                == "actuator_watchdog_reset_rejected"
            )
            assert samples["actuator"]["state"] == "FAULT_LATCHED"
            result["gazebo_reset_without_fresh_zero_denied"] = True
        if args.scenario == "manager-crash":
            assert result["fault_reason"] == "Manager heartbeat timeout", result
        result["two_second_target_met"] = stop - start <= 2
        if args.scenario != "gate-crash":
            assert not reset_result(), "Missing/reconciling manager must not permit reset"
        assert not reset_result(actuator_reset), "Unreconciled actuator reset must fail"
        if suspended:
            os.kill(suspended, signal.SIGCONT)
            suspended = None
        else:
            logfile = (ROOT / "logs/amr_smoke" / f"safety_restarted_{args.scenario}.log").open(
                "w"
            )
            replacement = subprocess.Popen(
                argv,
                env=env,
                cwd=ROOT,
                stdout=logfile,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        restarted_at = time.monotonic()
        deadline = restarted_at + 12
        while time.monotonic() < deadline:
            spin()
            state = http("/api/status")
            task = state["transport"].get("active_task") or {}
            if args.scenario == "gate-crash":
                assert samples["actuator"]["state"] == "FAULT_LATCHED"
            else:
                assert samples["safety"]["safety_state"] == "FAULT_LATCHED"
            assert samples["speed"] < 0.03 and samples["angular"] < 0.05
            if task.get("status") in {"failed", "cancelled"} and (
                args.scenario != "gate-crash"
                or (
                    time.monotonic() - restarted_at >= 2
                    and samples.get("safety_at", 0) > restarted_at
                    and samples.get("cmd_at", 0) > restarted_at
                    and samples.get("command", 1) < 1e-8
                )
            ):
                break
        else:
            raise AssertionError("Restarted process did not reconcile while remaining stopped")
        current = next(p for p in state["products"] if p["product_id"] == product["product_id"])
        assert current["current_location"] == "vision" and task.get("payload_loaded")
        if args.scenario != "gate-crash":
            assert not reset_result(), "Unresolved backend task must reject reset"
        assert not reset_result(actuator_reset), "Unresolved task must reject actuator reset"
        result.update(
            false_delivery=False, payload_retained=True, restart_did_not_clear_latch=True
        )
        # Explicit operator simulation reset aborts the held product; never calls it delivered.
        http("/api/reset", {})
        result["recovery_layers_reset"] = []
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            spin()
            # Any scenario can latch both layers. A successful ROS reset alone
            # is not proof that the actuator permits a newly authorized mission.
            action = recovery_action(samples, time.monotonic())
            if action == "reset_gate" and reset_result():
                result["recovery_layers_reset"].append("ros_safety")
            elif action == "reset_actuator" and reset_result(actuator_reset):
                result["recovery_layers_reset"].append("gazebo_actuator")
            elif action == "ready":
                break
        else:
            raise AssertionError(
                "Eligible operator recovery never became available for both layers: "
                f"gate={samples.get('safety')}, actuator={samples.get('actuator')}"
            )
        result["controlled_reset_succeeded"] = True
        new = http("/api/products", {"product_type": "red_block"})["product"]
        http("/api/start", {})
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            spin()
            state = http("/api/status")
            current = next(p for p in state["products"] if p["product_id"] == new["product_id"])
            if current["current_location"] == "vision":
                result["new_authorized_delivery_succeeded"] = True
                break
        else:
            raise AssertionError(
                f"New mission did not deliver after reset: {state['transport']}"
            )
        result["passed"] = True
    finally:
        result["trace"] = trace
        path = ROOT / "logs/amr_smoke" / f"safety_{args.scenario}_{time.time_ns()}.json"
        path.write_text(json.dumps(result, indent=2))
        print(json.dumps({k: v for k, v in result.items() if k != "trace"}), flush=True)
        print(f"Recorded {path}", flush=True)
        if suspended:
            os.kill(suspended, signal.SIGCONT)
        if replacement:
            os.killpg(replacement.pid, signal.SIGINT)
            try:
                replacement.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(replacement.pid, signal.SIGKILL)
                replacement.wait()
        if logfile:
            logfile.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
