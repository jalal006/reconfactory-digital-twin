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
```

The Gazebo sync process polls `/api/status`, creates product models, updates product
poses, removes products after reset, and updates machine status beacons.

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
