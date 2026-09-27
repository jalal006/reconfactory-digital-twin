"""Disrupt only an isolated smoke-test process group and verify real robot stopping."""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import subprocess
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def owned_process(
    group: int, marker: str, proc_root: Path = Path("/proc")
) -> tuple[int, list[str], dict]:
    def descendant(pid):
        # The launcher uses setsid for each service, so process-group equality
        # is insufficient. Require an actual parent chain to this test launcher.
        for _ in range(64):
            if pid == group:
                return True
            if pid <= 1:
                return False
            status = (proc_root / str(pid) / "status").read_text()
            pid = int(
                next(
                    line.split()[1] for line in status.splitlines() if line.startswith("PPid:")
                )
            )
        return False

    matches = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            argv = [a.decode() for a in (entry / "cmdline").read_bytes().split(b"\0") if a]
            if not any(a.endswith(marker) for a in argv):
                continue
            if not descendant(pid):
                continue
            env = dict(
                item.decode().split("=", 1)
                for item in (entry / "environ").read_bytes().split(b"\0")
                if b"=" in item
            )
            if env.get("ROS_DOMAIN_ID") != "73" or not env.get("GZ_PARTITION", "").startswith(
                "reconfactory_test_"
            ):
                raise RuntimeError("Refusing to disrupt a non-test process")
            matches.append((pid, argv, env))
        except (ProcessLookupError, FileNotFoundError, PermissionError):
            continue
    if len(matches) != 1:
        raise RuntimeError(f"Expected one owned {marker}; found {len(matches)}")
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--group", type=int, required=True)
    parser.add_argument(
        "--scenario", choices=["backend-outage", "manager-restart"], required=True
    )
    args = parser.parse_args()
    import rclpy
    from nav_msgs.msg import Odometry
    from rclpy.qos import qos_profile_sensor_data

    def http(path, payload=None):
        request = Request(
            args.url + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=0.4) as response:
            return json.load(response)

    rclpy.init()
    node = rclpy.create_node("reconfactory_resilience_verifier")
    samples = {}

    def odometry(msg):
        v = msg.twist.twist
        samples.update(
            at=time.monotonic(),
            speed=math.hypot(v.linear.x, v.linear.y),
            angular=abs(v.angular.z),
        )

    node.create_subscription(Odometry, "/odom", odometry, qos_profile_sensor_data)
    replacement = None
    suspended = None
    log = None
    try:
        product = http("/api/products", {"product_type": "red_block"})["product"]
        http("/api/start", {})
        deadline = time.monotonic() + 100
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
            state = http("/api/status")
            task = state["transport"].get("active_task") or {}
            pose = state["transport"].get("robot_pose") or {}
            if (
                task.get("destination") == "station_a"
                and task.get("phase") == "delivery"
                and task.get("status") == "navigating"
                and samples.get("speed", 0) > 0.1
                and 2.4 < pose.get("x", 0) < 3.7
            ):
                break
        else:
            raise RuntimeError("Did not observe loaded robot moving toward A")
        task_id = task["task_id"]
        start = time.monotonic()
        print(f"Injecting {args.scenario} while loaded and moving: {task_id}", flush=True)
        if args.scenario == "backend-outage":
            suspended, _, _ = owned_process(args.group, "scripts/run_factory.py")
            os.kill(suspended, signal.SIGSTOP)
        else:
            pid, argv, env = owned_process(args.group, "/amr_manager")
            os.kill(pid, signal.SIGKILL)
            limit = time.monotonic() + 3
            while Path(f"/proc/{pid}").exists() and time.monotonic() < limit:
                rclpy.spin_once(node, timeout_sec=0.05)
            if Path(f"/proc/{pid}").exists():
                raise RuntimeError("Old manager still exists; refusing duplicate manager")
            log = (ROOT / "logs/amr_smoke/restarted_manager.log").open("w")
            replacement = subprocess.Popen(
                argv,
                env=env,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        stopped_since = None
        stopped_at = None
        terminal_at = None
        deadline = start + 25
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
            now = time.monotonic()
            if replacement and replacement.poll() is not None:
                raise RuntimeError(
                    "Restarted manager exited during verification; inspect restarted_manager.log"
                )
            if (
                now - samples.get("at", 0) < 0.5
                and samples.get("speed", 1) < 0.03
                and samples.get("angular", 1) < 0.05
            ):
                stopped_since = stopped_since or now
                if now - stopped_since >= 0.5:
                    stopped_at = stopped_at or now
            else:
                stopped_since = None
                if terminal_at:
                    raise AssertionError("Robot moved after terminal held state")
            if suspended:
                if now - start < 3:
                    continue
                os.kill(suspended, signal.SIGCONT)
                suspended = None
            state = http("/api/status")
            active = state["transport"].get("active_task") or {}
            current = next(
                p for p in state["products"] if p["product_id"] == product["product_id"]
            )
            assert active.get("task_id") == task_id, "Unexpected replacement mission"
            assert current["current_location"] == "vision", "False delivery during outage"
            expected = "cancelled" if args.scenario == "backend-outage" else "failed"
            if active["status"] == expected and stopped_at:
                terminal_at = terminal_at or now
                assert active["payload_loaded"] and active["phase"] == "delivery"
                assert current["status"] == "paused", current
                if now - terminal_at >= 3:
                    locations = (state.get("gazebo_visuals") or {}).get("product_locations", {})
                    assert locations.get(product["product_id"]) == "amr_payload", locations
                    result = {
                        "scenario": args.scenario,
                        "task_id": task_id,
                        "stop_latency_s": stopped_at - start,
                        "terminal_latency_s": terminal_at - start,
                        "terminal_status": expected,
                        "held_station": current["current_location"],
                        "payload_loaded": True,
                        "no_extra_mission": True,
                        "stationary_hold_verified_s": 3,
                        "manager_alive_before_cleanup": replacement.poll() is None
                        if replacement
                        else None,
                    }
                    (ROOT / f"logs/amr_smoke/{args.scenario}.json").write_text(
                        json.dumps(result, indent=2)
                    )
                    print(f"PASS: {json.dumps(result)}", flush=True)
                    return
        raise RuntimeError(f"No safe held outcome within 25 seconds: {state['transport']}")
    finally:
        if suspended:
            os.kill(suspended, signal.SIGCONT)
        if replacement:
            os.killpg(replacement.pid, signal.SIGINT)
            try:
                replacement.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(replacement.pid, signal.SIGKILL)
                replacement.wait()
            print(f"Restarted manager cleanup exit: {replacement.returncode}", flush=True)
        if log:
            log.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
