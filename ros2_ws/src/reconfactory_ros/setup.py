from setuptools import find_packages, setup

package_name = "reconfactory_ros"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", ["launch/reconfactory_bridge.launch.py"]),
        ("share/" + package_name + "/config", ["config/bridge.yaml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="ReConFactory Maintainer",
    maintainer_email="maintainer@example.com",
    description="ROS 2 bridge nodes for ReConFactory.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "supervisor_node = reconfactory_ros.supervisor_node:main",
            "station_controller_node = reconfactory_ros.station_controller_node:main",
            "fault_detector_node = reconfactory_ros.fault_detector_node:main",
            "logger_node = reconfactory_ros.logger_node:main",
        ],
    },
)
