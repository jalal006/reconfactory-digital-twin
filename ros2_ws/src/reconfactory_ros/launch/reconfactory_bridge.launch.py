import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    backend_url = LaunchConfiguration("backend_url")
    project_root = LaunchConfiguration("project_root")
    enable_vision = LaunchConfiguration("enable_vision")
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "backend_url",
                default_value="http://127.0.0.1:8000",
                description="ReConFactory FastAPI backend URL.",
            ),
            DeclareLaunchArgument(
                "project_root",
                default_value=os.getenv("RECONFACTORY_PROJECT_ROOT", ""),
                description="Repository root used to import shared vision code.",
            ),
            DeclareLaunchArgument(
                "enable_vision",
                default_value=os.getenv("RECONFACTORY_ENABLE_VISION_NODE", "true"),
                description="Start the Gazebo camera OpenCV inspection node.",
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
            Node(
                package="reconfactory_ros",
                executable="vision_inspector_node",
                name="reconfactory_vision_inspector",
                condition=IfCondition(enable_vision),
                parameters=[
                    {
                        "backend_url": backend_url,
                        "project_root": project_root,
                        "image_topic": "/reconfactory/vision/image_raw",
                        "result_topic": "/reconfactory/vision/result",
                        "debug_image_topic": "/reconfactory/vision/debug_image",
                        "frame_id": "reconfactory_vision_camera_optical_frame",
                        "frame_window": 5,
                    }
                ],
                output="screen",
            ),
        ]
    )
