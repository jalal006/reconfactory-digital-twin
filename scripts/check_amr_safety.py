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
        samples.update(
            odom_at=time.monotonic(),
            speed=math.hypot(v.linear.x, v.linear.y),
            angular=abs(v.angular.z),
        )

    def command(msg):
        samples.update(cmd_at=time.monotonic(), command=math.hypot(msg.linear.x, msg.angular.z))

    def safety(msg):
        samples.update(safety=json.loads(msg.data), safety_at=time.monotonic())

    node.create_subscription(Odometry, "/odom", odom, 1)
    node.create_subscription(Twist, "/cmd_vel", command, 1)
    node.create_subscription(
        String,
        "/reconfactory/amr/safety/state",
        safety,
        QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL),
    )
    reset = node.create_client(Trigger, "/reconfactory/amr/safety/reset")

    def spin():
        for _ in range(8):
            rclpy.spin_once(node, timeout_sec=0.01)

    def reset_result():
        assert reset.wait_for_service(timeout_sec=2)
        future = reset.call_async(Trigger.Request())
        deadline = time.monotonic() + 3
        while not future.done() and time.monotonic() < deadline:
            spin()
        assert future.done(), "Reset service timeout"
        return future.result().success

    replacement, suspended, logfile = None, None, None
    result = {"scenario": args.scenario, "certified_safety": False}
    try:
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
                and samples.get("speed", 0) > 0.1
                and 2.4 < pose.get("x", 0) < 3.5
                and samples.get("command", 0) > 0.1
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
        marker = {
            "manager-crash": "/amr_manager",
            "gate-crash": "/safety_supervisor",
            "backend-outage": "scripts/run_factory.py",
        }[args.scenario]
        pid, argv, env = owned_process(args.group, marker)
        start = time.monotonic()
        os.kill(pid, signal.SIGSTOP if args.scenario == "backend-outage" else signal.SIGKILL)
        if args.scenario == "backend-outage":
            suspended = pid
        inhibit, stop, stable, fault_at = None, None, None, None
        deadline = start + (1.5 if args.scenario == "gate-crash" else 8)
        while time.monotonic() < deadline:
            spin()
            now = time.monotonic()
            s = samples.get("safety", {})
            if samples.get("cmd_at", 0) > start and samples.get("command", 1) < 1e-8:
                inhibit = inhibit or now
            if samples.get("safety_at", 0) > start and s.get("safety_state") == "FAULT_LATCHED":
                if fault_at is None:
                    result["fault_reason"] = s.get("safety_reason")
                    result["heartbeat_age_at_latch_ms"] = s.get("heartbeat_age_ms")
                fault_at = fault_at or now
            if (
                now - samples.get("odom_at", 0) < 0.5
                and samples.get("speed", 1) < 0.03
                and samples.get("angular", 1) < 0.05
            ):
                stable = stable or now
                if now - stable >= 0.3:
                    stop = stop or now
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
                }
            )
            if stop and now - stop >= 2 and args.scenario != "gate-crash":
                break
        result.update(
            command_inhibition_s=inhibit - start if inhibit else None,
            physical_stop_s=stop - start if stop else None,
            fault_latch_s=fault_at - start if fault_at else None,
            manager_restart_required_for_stop=False,
            trace=trace,
        )
        if args.scenario == "gate-crash":
            result.update(
                gate_failure_bounded_stop_verified=stop is not None,
                speed_after_gate_death=samples.get("speed"),
                limitation="DiffDrive retains last velocity: no supported command timeout. Diagnostic zero publisher used only for cleanup after gate death.",
            )
            cleanup = node.create_publisher(Twist, "/cmd_vel", 1)
            for _ in range(30):
                cleanup.publish(Twist())
                spin()
            assert samples["speed"] < 0.03 and samples["angular"] < 0.05
        else:
            assert inhibit and stop and fault_at, result
            if args.scenario == "manager-crash":
                assert result["fault_reason"] == "Manager heartbeat timeout", result
            result["two_second_target_met"] = stop - start <= 2
            assert not reset_result(), "Missing/reconciling manager must not permit reset"
            if suspended:
                os.kill(suspended, signal.SIGCONT)
                suspended = None
            else:
                logfile = (ROOT / "logs/amr_smoke/safety_restarted_manager.log").open("w")
                replacement = subprocess.Popen(
                    argv,
                    env=env,
                    cwd=ROOT,
                    stdout=logfile,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                spin()
                state = http("/api/status")
                task = state["transport"].get("active_task") or {}
                assert samples["safety"]["safety_state"] == "FAULT_LATCHED"
                assert samples["speed"] < 0.03 and samples["angular"] < 0.05
                if task.get("status") in {"failed", "cancelled"}:
                    break
            current = next(
                p for p in state["products"] if p["product_id"] == product["product_id"]
            )
            assert current["current_location"] == "vision" and task.get("payload_loaded")
            assert not reset_result(), "Unresolved backend task must reject reset"
            result.update(
                false_delivery=False, payload_retained=True, restart_did_not_clear_latch=True
            )
            # Explicit operator simulation reset aborts the held product; never calls it delivered.
            http("/api/reset", {})
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                spin()
                if reset_result():
                    break
            else:
                raise AssertionError("Eligible operator recovery never became available")
            result["controlled_reset_succeeded"] = True
            new = http("/api/products", {"product_type": "red_block"})["product"]
            http("/api/start", {})
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                spin()
                state = http("/api/status")
                current = next(
                    p for p in state["products"] if p["product_id"] == new["product_id"]
                )
                if current["current_location"] == "vision":
                    result["new_authorized_delivery_succeeded"] = True
                    break
            else:
                raise AssertionError(
                    f"New mission did not deliver after reset: {state['transport']}"
                )
        result["passed"] = True
    finally:
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
