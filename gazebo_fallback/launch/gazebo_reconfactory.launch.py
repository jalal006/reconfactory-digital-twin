from launch import LaunchDescription
from launch.actions import ExecuteProcess


def generate_launch_description():
    return LaunchDescription(
        [
            ExecuteProcess(
                cmd=[
                    "gz",
                    "sim",
                    "-r",
                    "gazebo_fallback/worlds/reconfactory.world.sdf",
                ],
                output="screen",
            )
        ]
    )
