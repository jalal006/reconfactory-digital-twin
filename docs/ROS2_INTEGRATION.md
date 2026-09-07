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
- `vision_inspector_node`: converts Gazebo camera images to OpenCV inspections

The normal Ubuntu/WSL launcher builds this package when its source changes,
starts four factory nodes plus the camera node when its dependencies are available,
and verifies that they are visible in the ROS graph.

## Topics

```text
/reconfactory/factory_state    std_msgs/String JSON snapshot
/reconfactory/faults           std_msgs/String JSON fault
/reconfactory/station_command  std_msgs/String JSON command
/reconfactory/factory_command  std_msgs/String JSON command
/reconfactory/vision/image_raw sensor_msgs/Image Gazebo camera frame
/reconfactory/vision/result    std_msgs/String JSON inspection result
/reconfactory/vision/debug_image sensor_msgs/Image annotated frame
```

`/reconfactory/vision/camera_info` is also bridged when Gazebo publishes camera
calibration metadata.

## Vision Node

```text
/reconfactory_vision_inspector
```

The node:

1. Reads `/api/status` from the FastAPI backend.
2. Only activates when a product is pending and Gazebo reports it at vision.
3. Converts `/reconfactory/vision/image_raw` using `cv_bridge`.
4. Runs the shared `OpenCVInspector` logic with color-only camera acceptance.
5. Aggregates five valid frames.
6. Publishes one JSON result on `/reconfactory/vision/result`.
7. Posts the same result to `/api/vision/result`.

The factory supervisor remains responsible for accepting, rejecting, routing,
and persisting the product.

## Normal Run

From the repository root:

```bash
bash run_ubuntu.sh
```

This starts FastAPI, ROS 2, Gazebo, and the Gazebo state bridge from one
terminal. ROS output is written to `logs/ros2.log`, and package build output is
written to `logs/ros2_build.log`.

## Manual Build

Inside a ROS 2 Jazzy environment:

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build
source install/setup.bash
```

Start the FastAPI backend first, then:

```bash
ros2 launch reconfactory_ros reconfactory_bridge.launch.py project_root:="$(dirname "$PWD")"
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

From the repository root in a sourced ROS terminal, run
`python3 scripts/check_vision_pipeline.py`. It samples actual image messages for
five seconds, checks required nodes/topics, detects duplicate factory node names,
and exits nonzero if a check fails. This does not prove product classification;
start result echo before spawning a normal and a wrong-color product.

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
/reconfactory_vision_inspector
```

Expected vision topics when Gazebo and the image bridge are running:

```text
/reconfactory/vision/image_raw
/reconfactory/vision/result
/reconfactory/vision/debug_image
```

Inspect the raw camera rate:

```bash
ros2 topic hz /reconfactory/vision/image_raw
```

Watch inspection JSON:

```bash
ros2 topic echo /reconfactory/vision/result
```

View the annotated result:

```bash
ros2 run rqt_image_view rqt_image_view /reconfactory/vision/debug_image
```

Optional RViz config:

```bash
rviz2 -d ros2_ws/src/reconfactory_ros/rviz/vision_debug.rviz
```
