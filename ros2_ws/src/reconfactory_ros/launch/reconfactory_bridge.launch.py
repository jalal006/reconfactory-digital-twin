from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    backend_url = LaunchConfiguration("backend_url")
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "backend_url",
                default_value="http://127.0.0.1:8000",
                description="ReConFactory FastAPI backend URL.",
            ),
            Node(
                package="reconfactory_ros",
                executable="supervisor_node",
                name="reconfactory_supervisor",
                parameters=[{"backend_url": backend_url}],
                output="screen",
            ),
            Node(
                package="reconfactory_ros",
                executable="station_controller_node",
                name="reconfactory_station_controller",
                parameters=[{"backend_url": backend_url}],
                output="screen",
            ),
            Node(
                package="reconfactory_ros",
                executable="fault_detector_node",
                name="reconfactory_fault_detector",
                parameters=[{"backend_url": backend_url}],
                output="screen",
            ),
            Node(
                package="reconfactory_ros",
                executable="logger_node",
                name="reconfactory_logger",
                output="screen",
            ),
        ]
    )
