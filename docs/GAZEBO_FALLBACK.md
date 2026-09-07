# Gazebo 3D Simulation

Gazebo is the selected open-source 3D simulation layer for this project.

Files:

```text
gazebo_fallback/worlds/reconfactory.world.sdf
gazebo_fallback/config/ros_gz_bridge.yaml
gazebo_fallback/launch/gazebo_reconfactory.launch.py
gazebo_fallback/scripts/sync_backend_to_gazebo.py
scripts/run_gazebo_sync.sh
```

## Run Concept

```text
FastAPI backend -> Gazebo sync process -> Gazebo world
Gazebo RGB camera -> ros_gz_bridge -> ROS 2 vision node -> FastAPI vision result
```

The Gazebo sync process polls `/api/status`, creates product models, updates product
poses, removes products after reset, and updates machine status beacons.

The vision station also contains a fixed RGB camera sensor. In Gazebo vision
mode, this camera makes the simulator part of the perception loop instead of
only a 3D visualization.

## Current Machine Setup

Gazebo is available through the ROS 2 Jazzy environment:

```bash
source /opt/ros/jazzy/setup.bash
gz sim --help
```

## Run

Normal run, one Ubuntu/WSL terminal:

```bash
cd /path/to/production_line
bash run_ubuntu.sh
```

This starts the FastAPI backend, Gazebo world, and live Gazebo synchronization.
Press Ctrl+C in the same terminal to stop all of it.

When ROS 2, Gazebo, `ros_gz_bridge`, and `cv_bridge` are available, the
launcher selects:

```bash
VISION_SOURCE=gazebo
```

Otherwise it falls back to:

```bash
VISION_SOURCE=synthetic
```

Use these separate commands only when debugging individual pieces:

```bash
cd /path/to/production_line
bash scripts/run_gazebo.sh
bash scripts/run_gazebo_sync.sh
```

Optional raw state publishing:

```bash
cd /path/to/production_line
bash gazebo_fallback/scripts/publish_backend_state.sh
```

The browser page remains the main control surface. Gazebo is an external 3D view of
the same factory state while the sync bridge is running.

## Gazebo Camera

The camera is defined inside:

```text
gazebo_fallback/worlds/reconfactory.world.sdf
```

The world loads `gz-sim-sensors-system`; without that plugin the camera model
exists in Gazebo but no image frames are published.

It also explicitly loads Physics, UserCommands (create/remove/set-pose services),
and SceneBroadcaster. The lens sits below its opaque housing. Removing
UserCommands prevents the backend sync process from spawning products.

Sensor:

```text
model: vision_camera_station
sensor: rgb_inspection_camera
topic: /reconfactory/vision/image_raw
resolution: 640x480
rate: 15 Hz
```

The bridge config is:

```text
gazebo_fallback/config/ros_gz_bridge.yaml
```

It maps:

```text
/reconfactory/vision/image_raw   gz.msgs.Image -> sensor_msgs/msg/Image
/reconfactory/vision/camera_info gz.msgs.CameraInfo -> sensor_msgs/msg/CameraInfo
```

## Verify Camera Mode

Run the normal stack:

```bash
bash run_ubuntu.sh
```

Check the ROS graph:

```bash
ros2 node list
ros2 topic list | grep reconfactory
```

Check camera images:

```bash
ros2 topic hz /reconfactory/vision/image_raw
```

Check inspection results:

```bash
ros2 topic echo /reconfactory/vision/result
```

Open the debug image:

```bash
ros2 run rqt_image_view rqt_image_view /reconfactory/vision/debug_image
```

Or open the optional RViz layout:

```bash
rviz2 -d ros2_ws/src/reconfactory_ros/rviz/vision_debug.rviz
```

Camera mode checks color only. Use a normal product and a `wrong_colour` product
for the pass/fail demo. Start the result listener before spawning: decisions
are one-shot, and the debug topic updates only during inspection. See
[requirements audit](VISION_ACCEPTANCE_AUDIT.md) for verification evidence.

## Timing

The browser uses Gazebo station reports to trigger its own movement. If reports
become stale, a started movement finishes and then waits; it does not switch to
backend positions or reverse to an earlier station when updates resume. A reset
clears this per-product synchronization state. Explicit recovery routes remain
available.

Products in Gazebo are kinematic with gravity disabled. While waiting for a
transport timer or station dwell, the sync process does not resend unchanged
poses. It sends the new pose at the transfer boundary and publishes station
updates before creating/removing decorative route arrows. Station dwell and
transport durations themselves have not been shortened.

Integration discovery and recovery experiments run outside the API event loop,
so slow optional checks do not hold up Start/Pause or WebSocket updates. The Start
button displays its pending state immediately and prevents duplicate requests.
