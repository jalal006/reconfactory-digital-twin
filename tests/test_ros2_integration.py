from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "ros2_ws" / "src" / "reconfactory_ros"
MODULE_ROOT = PACKAGE_ROOT / "reconfactory_ros"


def load_station_controller_module():
    package_parent = str(PACKAGE_ROOT)
    if package_parent not in sys.path:
        sys.path.insert(0, package_parent)
    path = MODULE_ROOT / "station_controller_node.py"
    spec = importlib.util.spec_from_file_location(
        "reconfactory_ros.station_controller_node", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    def post(self, path: str, payload=None):
        self.calls.append((path, payload))
        return {"ok": True}


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"command": "start"}, ("/api/start", None)),
        ({"command": "pause"}, ("/api/stop", None)),
        ({"command": "reset"}, ("/api/reset", None)),
        ({"command": "emergency_stop"}, ("/api/emergency-stop", None)),
        (
            {"command": "add_product", "product_type": "red_block"},
            (
                "/api/products",
                {"product_type": "red_block", "defect_flags": []},
            ),
        ),
        (
            {"command": "fault", "machine_id": "station_a", "fault_type": "overheat"},
            (
                "/api/faults",
                {
                    "machine_id": "station_a",
                    "fault_type": "overheat",
                    "reason": "ROS 2 command",
                },
            ),
        ),
        (
            {"command": "recover", "machine_id": "station_a"},
            ("/api/recover", {"machine_id": "station_a"}),
        ),
    ],
)
def test_ros_command_dispatch(payload, expected):
    module = load_station_controller_module()
    client = FakeClient()

    assert module.dispatch_command(client, payload) == {"ok": True}
    assert client.calls == [expected]


def test_ros_command_dispatch_rejects_unknown_command():
    module = load_station_controller_module()

    with pytest.raises(ValueError, match="Unsupported ROS 2 command"):
        module.dispatch_command(FakeClient(), {"command": "invalid"})


def test_ros_launch_accepts_runtime_backend_url():
    launch_source = (PACKAGE_ROOT / "launch" / "reconfactory_bridge.launch.py").read_text(
        encoding="utf-8"
    )

    assert "DeclareLaunchArgument(" in launch_source
    assert 'LaunchConfiguration("backend_url")' in launch_source
    assert launch_source.count('parameters=[{"backend_url": backend_url}]') == 3


def test_one_command_runner_starts_and_checks_ros_nodes():
    runner = (ROOT / "run_ubuntu.sh").read_text(encoding="utf-8")

    assert "bash scripts/run_ros_bridge.sh" in runner
    assert "ROS_READY=false" in runner
    assert '"/reconfactory_supervisor"' in runner
    assert '"/reconfactory_station_controller"' in runner
    assert '"/reconfactory_fault_detector"' in runner
    assert '"/reconfactory_logger"' in runner
