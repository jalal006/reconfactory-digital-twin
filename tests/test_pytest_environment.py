"""Keep normal unit tests independent of auto-discovered ROS launch plugins."""

import os
import subprocess
import sys
from pathlib import Path


def test_ros_launch_plugins_are_not_imported(tmp_path):
    root = Path(__file__).resolve().parents[1]
    metadata = tmp_path / "fake_ros_launch-1.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text("Name: fake-ros-launch\nVersion: 1.0\n")
    (metadata / "entry_points.txt").write_text(
        "[pytest11]\nlaunch_testing = broken_ros_plugin\nlaunch_ros = broken_ros_plugin\n"
    )
    (tmp_path / "broken_ros_plugin.py").write_text(
        "raise RuntimeError('ROS launch plugin must not load in the unit suite')\n"
    )
    env = dict(os.environ)
    env.pop("PYTEST_DISABLE_PLUGIN_AUTOLOAD", None)
    env.pop("PYTEST_ADDOPTS", None)
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(tmp_path), env.get("PYTHONPATH", "")) if part
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/test_energy.py"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "test_energy_equation_and_payload" in result.stdout
