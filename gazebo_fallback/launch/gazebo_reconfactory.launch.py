from pathlib import Path

from launch import LaunchDescription
from launch.actions import ExecuteProcess


def generate_launch_description():
    root = Path(__file__).resolve().parents[2]
    world = root / "gazebo_fallback" / "worlds" / "reconfactory.world.sdf"
    bridge_config = root / "gazebo_fallback" / "config" / "ros_gz_bridge.yaml"
    return LaunchDescription(
        [
            ExecuteProcess(
                cmd=[
                    "gz",
                    "sim",
                    "-r",
                    str(world),
                ],
                output="screen",
            ),
            ExecuteProcess(
                cmd=[
                    "ros2",
                    "run",
                    "ros_gz_bridge",
                    "parameter_bridge",
                    "--ros-args",
                    "-p",
                    f"config_file:={bridge_config}",
                ],
                output="screen",
            ),
        ]
    )
