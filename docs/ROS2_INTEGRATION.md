# ROS 2 Integration

The ROS 2 package is in:

```text
ros2_ws/src/reconfactory_ros
```

It provides:

- `supervisor_node`: publishes FastAPI factory snapshots
- `station_controller_node`: accepts recovery and fault commands
- `fault_detector_node`: publishes new fault records
- `logger_node`: logs summary state

The normal Ubuntu/WSL launcher builds this package when its source changes,
starts all four nodes, and verifies that they are visible in the ROS graph.

## Topics

```text
/reconfactory/factory_state    std_msgs/String JSON snapshot
/reconfactory/faults           std_msgs/String JSON fault
/reconfactory/station_command  std_msgs/String JSON command
/reconfactory/factory_command  std_msgs/String JSON command
```

## Normal Run

From the repository root:

```bash
bash run_ubuntu.sh
```

This starts FastAPI, ROS 2, Gazebo, and the Gazebo state bridge from one
terminal. ROS output is written to `logs/ros2.log`, and package build output is
written to `logs/ros2_build.log`.

## Manual Build

Inside a ROS 2 Jazzy or Humble environment:

```bash
cd ros2_ws
colcon build
source install/setup.bash
```

Start the FastAPI backend first, then:

```bash
ros2 launch reconfactory_ros reconfactory_bridge.launch.py
```

Or from the repository root:

```bash
bash scripts/run_ros_bridge.sh
```

`run_ros_bridge.sh` accepts the backend URL through
`RECONFACTORY_BACKEND_URL` and skips `colcon build` when the package is already
up to date.

## Command Examples

Start production:

```bash
ros2 topic pub --once /reconfactory/factory_command std_msgs/msg/String \
  "{data: '{\"command\":\"start\"}'}"
```

Add a product:

```bash
ros2 topic pub --once /reconfactory/factory_command std_msgs/msg/String \
  "{data: '{\"command\":\"add_product\",\"product_type\":\"red_block\"}'}"
```

Inject a station fault:

```bash
ros2 topic pub --once /reconfactory/station_command std_msgs/msg/String \
  "{data: '{\"command\":\"fault\",\"machine_id\":\"station_a\",\"fault_type\":\"overheat\"}'}"
```

Supported commands are `start`, `pause`, `stop`, `reset`, `emergency_stop`,
`add_product`, `fault`, and `recover`.

## Runtime Verification

```bash
ros2 node list
ros2 topic list | grep reconfactory
```

Expected nodes:

```text
/reconfactory_supervisor
/reconfactory_station_controller
/reconfactory_fault_detector
/reconfactory_logger
```
