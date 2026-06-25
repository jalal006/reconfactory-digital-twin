"""Detect optional external digital-twin integrations."""

from __future__ import annotations

import importlib.util
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class IntegrationStatus:
    name: str
    installed: bool
    command: str | None = None
    version: str | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "installed": self.installed,
            "command": self.command,
            "version": self.version,
            "detail": self.detail,
        }


def check_integrations() -> dict[str, object]:
    statuses = [
        _python_status(),
        _fastapi_status(),
        _ros2_status(),
        _gazebo_status(),
        _colcon_status(),
        _opcua_status(),
    ]
    return {
        "platform": platform.platform(),
        "workspace": str(ROOT),
        "items": [status.to_dict() for status in statuses],
        "summary": {status.name: status.installed for status in statuses},
    }


def _python_status() -> IntegrationStatus:
    return IntegrationStatus(
        name="python",
        installed=True,
        command=shutil.which("python") or shutil.which("python3"),
        version=platform.python_version(),
        detail="Backend runtime is available.",
    )


def _fastapi_status() -> IntegrationStatus:
    installed = importlib.util.find_spec("fastapi") is not None
    return IntegrationStatus(
        name="fastapi",
        installed=installed,
        detail="Dashboard backend dependency.",
    )


def _opcua_status() -> IntegrationStatus:
    installed = importlib.util.find_spec("asyncua") is not None
    return IntegrationStatus(
        name="opcua_asyncua",
        installed=installed,
        detail=(
            "Optional OPC UA dependency is installed."
            if installed
            else "Optional. Install with: python -m pip install asyncua"
        ),
    )


def _colcon_status() -> IntegrationStatus:
    command = shutil.which("colcon")
    if not command:
        command = _bash_command_path("colcon")
    return IntegrationStatus(
        name="colcon",
        installed=bool(command),
        command=command,
        detail="ROS 2 workspace build tool.",
    )


def _ros2_status() -> IntegrationStatus:
    command = shutil.which("ros2") or _bash_command_path("ros2")
    version = None
    detail = "ROS 2 command is available." if command else "ROS 2 command not found."
    if command:
        ros_distro = _bash_output(
            "source /opt/ros/jazzy/setup.bash 2>/dev/null || true; echo $ROS_DISTRO"
        )
        version = ros_distro or None
    return IntegrationStatus(
        name="ros2",
        installed=bool(command),
        command=command,
        version=version,
        detail=detail,
    )


def _gazebo_status() -> IntegrationStatus:
    command = shutil.which("gz") or shutil.which("gazebo") or _bash_command_path("gz")
    version = None
    if command:
        version = _bash_output(
            "source /opt/ros/jazzy/setup.bash 2>/dev/null || true; "
            "gz sim --help >/dev/null 2>&1 && echo gz-sim || gz --version 2>/dev/null | head -1"
        )
    return IntegrationStatus(
        name="gazebo_gz",
        installed=bool(command),
        command=command,
        version=version,
        detail=(
            "Gazebo Sim CLI is available through ROS/Gazebo tools."
            if command
            else "Gazebo command not found on PATH."
        ),
    )


def _bash_command_path(command: str) -> str | None:
    output = _bash_output(
        f"source /opt/ros/jazzy/setup.bash 2>/dev/null || true; command -v {command}"
    )
    return output or None


def _bash_output(script: str) -> str:
    if platform.system().lower() == "windows":
        wsl = shutil.which("wsl")
        if not wsl:
            return ""
        cmd = [wsl, "-e", "bash", "-lc", script]
    else:
        cmd = ["bash", "-lc", script]
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
