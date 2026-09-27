"""Run a bounded, isolated AMR demo through the normal Ubuntu launcher."""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goal-timeout", type=float, default=100.0)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--manual-drive", action="store_true")
    mode.add_argument(
        "--resilience",
        choices=["backend-outage", "manager-restart"],
        help="Verify fail-closed behavior during loaded navigation",
    )
    mode.add_argument(
        "--fault-replan",
        action="store_true",
        help="Fault A during loaded delivery; verify cancellation and delivery to B",
    )
    mode.add_argument(
        "--factory-only",
        action="store_true",
        help="Check sensors/planning and run production without preliminary manual goals",
    )
    mode.add_argument(
        "--navigation-only",
        nargs="+",
        metavar="STATION",
        help="Plan all station pairs, navigate these goals, then stop without production",
    )
    mode.add_argument(
        "--vision-only",
        action="store_true",
        help="Verify pickup, delivery and real camera inspection, then stop",
    )
    args = parser.parse_args()
    if not math.isfinite(args.goal_timeout) or args.goal_timeout <= 0:
        parser.error("--goal-timeout must be finite and positive")
    if sys.platform != "linux":
        raise SystemExit("Run from Ubuntu/WSL after sourcing ROS 2 Jazzy")
    logs = ROOT / "logs/amr_smoke"
    logs.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        **os.environ,
        "PORT": str(port),
        "TRANSPORT_MODE": "amr",
        "VISION_SOURCE": "gazebo",
        "GAZEBO_HEADLESS": "1",
        "ROS_DOMAIN_ID": "73",
        "GZ_PARTITION": f"reconfactory_test_{os.getpid()}",
        "RECONFACTORY_LOG_DIR": str(logs),
        "RECONFACTORY_DB_PATH": str(logs / f"test_{os.getpid()}.db"),
    }
    if args.manual_drive:
        env["RECONFACTORY_AMR_NAV2"] = "false"
    url = f"http://127.0.0.1:{port}"

    def http(path, payload=None):
        request = Request(
            url + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=2) as response:
            return json.load(response)

    with (logs / "launcher.log").open("w") as log:
        process = subprocess.Popen(
            ["bash", "run_ubuntu.sh"],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            print(f"Isolated stack on {url}; logs {logs}", flush=True)
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Launcher exited; inspect launcher.log")
                try:
                    if http("/api/transport").get("ready") or args.manual_drive:
                        break
                except OSError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("AMR did not become ready in 180 seconds")
            if args.manual_drive:
                subprocess.run(
                    [
                        "/usr/bin/python3",
                        "scripts/check_amr_pipeline.py",
                        "--manual-drive",
                        "--timeout",
                        "120",
                    ],
                    cwd=ROOT,
                    env=env,
                    check=True,
                    timeout=140,
                )
                return
            goals = args.navigation_only or (
                []
                if args.vision_only or args.factory_only or args.fault_replan or args.resilience
                else ["home", "input_queue", "vision"]
            )
            subprocess.run(
                [
                    "/usr/bin/python3",
                    "scripts/check_amr_pipeline.py",
                    "--plan-all",
                    "--goals",
                    *goals,
                    "--timeout",
                    str(args.goal_timeout),
                ],
                cwd=ROOT,
                env=env,
                check=True,
                timeout=60 + args.goal_timeout * (len(goals) + 1),
            )
            if args.navigation_only:
                return
            if args.resilience:
                subprocess.run(
                    [
                        "/usr/bin/python3",
                        "scripts/check_amr_resilience.py",
                        "--url",
                        url,
                        "--group",
                        str(process.pid),
                        "--scenario",
                        args.resilience,
                    ],
                    cwd=ROOT,
                    env=env,
                    check=True,
                    timeout=180,
                )
                return
            product = http("/api/products", {"product_type": "red_block"})["product"]
            http("/api/start", {})
            started = time.monotonic()
            replan = {}
            seen_tasks = set()
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                state = http("/api/status")
                (logs / "last_state.json").write_text(
                    json.dumps(state, indent=2), encoding="utf-8"
                )
                task = (state.get("transport") or {}).get("active_task") or {}
                if task.get("status") in {"failed", "cancelled"} and not (
                    args.fault_replan and task.get("replan_state") == "awaiting_replan"
                ):
                    raise RuntimeError(f"Transport failed: {task}")
                p = next(
                    p for p in state["products"] if p["product_id"] == product["product_id"]
                )
                inspection = state.get("last_inspection_result") or {}
                if args.fault_replan:
                    now = time.monotonic() - started
                    pose = state["transport"].get("robot_pose") or {}
                    if task and task["task_id"] not in seen_tasks:
                        seen_tasks.add(task["task_id"])
                        print(f"Task at {now:.2f}s: {json.dumps(task)}", flush=True)
                    if (
                        not replan
                        and task.get("destination") == "station_a"
                        and task.get("phase") == "delivery"
                        and task.get("status") == "navigating"
                        and 2.4 < pose.get("x", 0) < 3.8
                    ):
                        replan = {
                            "old_task_id": task["task_id"],
                            "fault_at_s": now,
                            "fault_pose": pose,
                            "payload_loaded": task["payload_loaded"],
                        }
                        http(
                            "/api/faults", {"machine_id": "station_a", "fault_type": "overheat"}
                        )
                        print(f"Injected in-flight fault: {json.dumps(replan)}", flush=True)
                    if task.get("supersedes_task_id") == replan.get("old_task_id") and replan:
                        if "replacement_at_s" not in replan:
                            assert (
                                task["destination"] == "station_b"
                                and task["phase"] == "delivery"
                            ), task
                            assert (
                                task["payload_loaded"] and p["current_location"] == "vision"
                            ), task
                            replan.update(
                                replacement_at_s=now,
                                replacement_pose=pose,
                                cancel_latency_s=task["cancel_latency_s"],
                                replan_latency_s=task["replan_latency_s"],
                                new_task_id=task["task_id"],
                            )
                    if replan and p["current_location"] == "station_b":
                        replan.setdefault("delivered_to_b_at_s", now)
                        if p["status"] == "processing":
                            replan["processing_at_b"] = True
                    if replan and task.get("payload_loaded"):
                        locations = (state.get("gazebo_visuals") or {}).get(
                            "product_locations", {}
                        )
                        if locations.get(p["product_id"]) == "amr_payload":
                            replan["gazebo_payload_reported"] = True
                if args.vision_only and inspection:
                    assert inspection.get("method") == "gazebo_camera" and inspection.get(
                        "passed"
                    ), inspection
                    print(
                        f"PASS: robot-delivered cargo inspected from real camera pixels: {json.dumps(inspection)}",
                        flush=True,
                    )
                    return
                if p["status"] in {"completed", "rejected"}:
                    if args.fault_replan:
                        assert replan.get("processing_at_b"), replan
                        assert replan.get("gazebo_payload_reported"), replan
                        replan["completed_at_s"] = time.monotonic() - started
                        replan["recovery_time_s"] = (
                            replan["delivered_to_b_at_s"] - replan["fault_at_s"]
                        )
                        (logs / "replan_result.json").write_text(
                            json.dumps(replan, indent=2), encoding="utf-8"
                        )
                        print(f"Replan measurements: {json.dumps(replan)}", flush=True)
                    print(f"Factory result: {json.dumps(p)}", flush=True)
                    assert p["status"] == "completed", "Normal product did not pass"
                    assert inspection.get("method") == "gazebo_camera" and inspection.get(
                        "passed"
                    ), f"Real camera inspection did not pass: {inspection}"
                    assert p["current_location"] == "accepted_output", p
                    print(
                        "PASS: supervisor -> manager -> Nav2 -> delivery -> production completion",
                        flush=True,
                    )
                    return
                time.sleep(0.1 if args.fault_replan else 1)
            raise RuntimeError("Factory delivery demo timed out")
        finally:
            try:
                os.killpg(process.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            # Stop remaining children in this test's process group only.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            print("Isolated test stack stopped", flush=True)


if __name__ == "__main__":
    main()
