"""Robot + Nav2 in an already-running factory world; never starts another Gazebo."""

from pathlib import Path

import xacro
import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def launch_nodes(context):
    share = Path(get_package_share_directory("reconfactory_amr"))
    config = str(share / "config/nav2.yaml")
    stations_file = share / "config/stations.yaml"
    home = yaml.safe_load(stations_file.read_text())["stations"]["home"]
    description = xacro.process_file(str(share / "urdf/amr.urdf.xacro")).toxml()
    nodes = [
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            parameters=[{"use_sim_time": True, "robot_description": description}],
        ),
        Node(
            package="ros_gz_sim",
            executable="create",
            arguments=[
                "-world",
                "reconfactory_world",
                "-name",
                "reconfactory_amr",
                "-topic",
                "robot_description",
                "-x",
                str(home["x"]),
                "-y",
                str(home["y"]),
                "-z",
                "0.02",
                "-Y",
                str(home["yaw"]),
            ],
        ),
        Node(
            package="ros_gz_bridge",
            executable="parameter_bridge",
            name="amr_gazebo_bridge",
            parameters=[{"config_file": str(share / "config/bridge.yaml")}],
        ),
    ]
    if LaunchConfiguration("enable_nav2").perform(context).lower() == "true":
        nodes.extend(
            [
                Node(
                    package="nav2_map_server",
                    executable="map_server",
                    name="map_server",
                    parameters=[
                        config,
                        {"yaml_filename": str(share / "maps/reconfactory_map.yaml")},
                    ],
                ),
                Node(
                    package="nav2_map_server",
                    executable="map_server",
                    name="localization_map_server",
                    parameters=[
                        {
                            "use_sim_time": True,
                            "frame_id": "map",
                            "topic_name": "localization_map",
                            "yaml_filename": str(share / "maps/reconfactory_lidar_map.yaml"),
                        }
                    ],
                ),
                Node(
                    package="nav2_amcl",
                    executable="amcl",
                    name="amcl",
                    remappings=[("map", "localization_map")],
                    parameters=[
                        config,
                        {f"initial_pose.{key}": float(value) for key, value in home.items()},
                    ],
                ),
            ]
        )
        servers = [
            ("nav2_planner", "planner_server"),
            ("nav2_controller", "controller_server"),
            ("nav2_behaviors", "behavior_server"),
            ("nav2_bt_navigator", "bt_navigator"),
            ("nav2_velocity_smoother", "velocity_smoother"),
        ]
        for package, name in servers:
            remaps = [("cmd_vel", "cmd_vel_nav")]
            if name == "velocity_smoother":
                remaps.append(("cmd_vel_smoothed", "cmd_vel"))
            nodes.append(
                Node(
                    package=package,
                    executable=name,
                    name=name,
                    parameters=[config],
                    remappings=remaps,
                )
            )
        for suffix, names in [
            ("localization", ["map_server", "localization_map_server", "amcl"]),
            ("navigation", [name for _, name in servers]),
        ]:
            nodes.append(
                Node(
                    package="nav2_lifecycle_manager",
                    executable="lifecycle_manager",
                    name=f"lifecycle_manager_{suffix}",
                    parameters=[{"use_sim_time": True, "autostart": True, "node_names": names}],
                )
            )
        if LaunchConfiguration("enable_manager").perform(context).lower() == "true":
            nodes.append(
                Node(
                    package="reconfactory_amr",
                    executable="amr_manager",
                    parameters=[
                        {
                            "use_sim_time": True,
                            "project_root": LaunchConfiguration("project_root"),
                            "backend_url": LaunchConfiguration("backend_url"),
                            "stations_file": str(stations_file),
                        }
                    ],
                )
            )
    return nodes


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument("project_root", default_value=""),
            DeclareLaunchArgument("backend_url", default_value="http://127.0.0.1:8000"),
            DeclareLaunchArgument("enable_nav2", default_value="true"),
            DeclareLaunchArgument("enable_manager", default_value="true"),
            OpaqueFunction(function=launch_nodes),
        ]
    )
