# Single-AMR Navigation

This opt-in milestone uses one differential-drive robot, a static factory map,
AMCL and standard ROS 2 Jazzy Nav2 components. It does not use SLAM, custom path
planning, fleet scheduling or grasping. Default simulated transport is unchanged.

## Architecture And Authority

```text
FactorySupervisor (product, recipe, fault and quality authority)
  -> FactoryTransport / TransportRequest
  -> GET /api/transport
  -> /reconfactory/amr/task (JSON String)
  -> /reconfactory_amr_manager
  -> NavigateToPose: origin, then destination
  -> Nav2 -> /cmd_vel -> Gazebo differential-drive AMR
  <- /scan + /odom + TF
  -> /reconfactory/amr/status (JSON String)
  -> POST /api/transport/status
  -> confirmed product arrival -> station processing

Gazebo vision camera -> ROS Image -> existing OpenCV node -> supervisor
```

The manager is a transport executor, not a second production scheduler. It
polls the authoritative task at 4 Hz, validates topic tasks against that task,
and reports each state transition once. HTTP retries preserve transition order;
duplicate task IDs and duplicate/stale statuses cannot cause another delivery.
In standalone mode (`backend_url:=''`) topic tasks are accepted without a backend.
Do not run standalone alongside production supervision.

The supervisor allows one active transport. It reserves a compatible, unoccupied
station using the existing scheduler. Products remain `in_transit` at their last
confirmed station during navigation. After pickup succeeds, payload placement
follows the robot. Only destination action success permits location change and
station processing. Accepted/rejected outputs are also gated on delivery.

The existing Gazebo sync process is the only product-pose writer. AMR mode skips
its old conveyor timers and route replay. It renders cargo without the legacy
display cart, on a tray above the LiDAR scan plane. Loading and unloading are
logical placements between a station and the robot, not simulated grasping.
The browser remains a station schematic: it animates confirmed deliveries and
shows task state; it is not a live map of the robot's aisle trajectory.

## Frames And Topics

```text
map                  AMCL owns map -> odom
  odom               Gazebo DiffDrive owns odom -> base_footprint
    base_footprint   robot_state_publisher owns all robot joint transforms
      base_link
        laser_link
        left_wheel / right_wheel / front_caster / rear_caster
```

There is no static map-to-odom publisher. One robot_state_publisher is launched.
Initial AMCL pose comes from the same `home` config as the robot spawn pose.

| ROS Interface | Type / Owner |
|---|---|
| `/scan` | `sensor_msgs/LaserScan`, Gazebo GPU LiDAR through robot bridge |
| `/odom` | `nav_msgs/Odometry`, Gazebo wheel odometry through robot bridge |
| `/cmd_vel` | `geometry_msgs/Twist`, Nav2 velocity smoother to DiffDrive |
| `/tf`, `/tf_static` | AMCL, DiffDrive bridge, robot_state_publisher |
| `/joint_states` | `sensor_msgs/JointState`, Gazebo wheel joints |
| `/clock` | `rosgraph_msgs/Clock`, Gazebo; all navigation nodes use sim time |
| `/navigate_to_pose` | `nav2_msgs/action/NavigateToPose` |
| `/reconfactory/amr/task` | `std_msgs/String`, JSON transport request |
| `/reconfactory/amr/status` | `std_msgs/String`, JSON transition result |

The existing camera bridge is separate and retains all camera topics. The AMR
bridge adds robot topics only, so it does not duplicate the camera bridge.

## Navigation And Map Configuration

Package: `ros2_ws/src/reconfactory_amr/`.

- `urdf/amr.urdf.xacro`: 12 kg steel base, two 0.10 m radius wheels separated by
  0.345 m, passive low-friction casters, tray, 360-beam 10 Hz planar LiDAR.
- `config/nav2.yaml`: Smac 2D global planner and standard Regulated Pure Pursuit
  controller, with initial heading alignment for sharp direction changes,
  map_server, AMCL, behavior server, BT navigator and velocity smoother; standard
  lifecycle managers bring these up. Maximum commanded speed 0.45 m/s, controller 20 Hz,
  position tolerance 0.12 m. Logical loading does not require a final yaw: the
  planner uses the final path approach heading instead of a fixed machine-facing
  heading. StoppedGoalChecker
  requires speed <= 0.05 m/s and angular speed <= 0.1 rad/s at the dock, with
  current position rechecked (not latched). A conservative 0.31 m radius encloses the tray
  corners in every orientation in both costmaps. Smac's cost travel multiplier
  is 8.0 to favor clearance without inventing a larger physical collision radius;
  obstacle and inflation layers are enabled.
  Inflation extends 0.8 m with a scaling factor of 3.0, giving the cost-aware
  planner a gradual clearance penalty instead of a narrow band at obstacles.
  Both costmaps include the static map: conservative collision envelopes may
  extend beyond surfaces visible to rendered LiDAR. Pure Pursuit tracks a 0.6 m
  lookahead point, scales speed for curvature and obstacle proximity, and retains
  collision prediction. Approach speed can fall to 0.03 m/s, below the stopped
  checker threshold. This replaces the MPPI/Rotation Shim combination that could
  accumulate unnecessary turns near docks. The BT action acknowledgement timeout
  is 1,000 ms instead of 20 ms to tolerate WSL scheduling jitter; this is not a
  delay added to normal movement or a navigation completion timeout.
- `config/stations.yaml`: the single source of named docking poses. Canonical
  supervisor names are `input_queue`, `vision`, `station_a`, `station_b`,
  `quality`, `accepted_output`, `reject_output`, plus `home`.
  Station yaw is nominal; the planner uses the approach heading and arrival does
  not require matching the nominal yaw. Home yaw determines the initial pose.
- `config/factory_layout.yaml`: AMR-only machine positions and 13 x 9 m floor.
  Workcells face a central aisle with more than 2 m of clear width. Docks are
  on its edges; both drills can reach Quality without a perimeter lap.
- `maps/reconfactory_map.yaml` and `.pgm`: 0.05 m occupancy map. Docking poses are
  in aisles beside machines, not inside the station's product placement surface.
- `maps/reconfactory_lidar_map.yaml` and `.pgm`: a separate 0.05 m localization
  map sliced from rendered box geometry at the robot's configured LiDAR height.
  `localization_map_server` publishes `/localization_map` to AMCL only. The
  navigation map retains collision envelopes and floor limits; the localization
  map excludes invisible envelopes, elevated rails and virtual floor-edge walls.
  This slice approximates box visuals; non-box geometry needs explicit treatment
  if added to the world at scan height.
  Both use the same origin/frame. AMCL remains the only map-to-odom publisher.
- `scripts/generate_amr_map.py`: derives the map and an AMR-only collision world
  from the original factory equipment. It moves each machine with its details
  (including the Vision camera), replaces connecting belts with AMR access space,
  moves the fence and maintenance cart to the service perimeter, and expands the
  floor/walls. Physical collision checks remain enabled. Product placement reads
  the generated station surfaces, not the original conveyor coordinates.
  Output world is ignored at `data/amr/factory.world.sdf`; the original factory
  world and its simulated conveyor mode remain untouched. Map images and YAML
  origins are regenerated together from the layout configuration.

If machine geometry changes, regenerate and rebuild. Test docking clearance
before changing station coordinates. The robot navigates in ground-level aisles,
not along the elevated conveyors. See the official
[Nav2 Gazebo setup](https://docs.nav2.org/jazzy/configuration_and_development/first_time_robot_setup_guide/gazebo/)
and [odometry setup](https://docs.nav2.org/jazzy/configuration_and_development/first_time_robot_setup_guide/odom/setup_odom_gz/).
Clearance tuning follows the [Nav2 inflation guidance](https://docs.nav2.org/rolling/configuration_and_development/tuning_guide/).
Controller settings follow the Jazzy implementation of
[Regulated Pure Pursuit](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_regulated_pure_pursuit_controller/src/regulated_pure_pursuit_controller.cpp),
with conservative differential-drive velocity/acceleration limits and
[StoppedGoalChecker](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_controller/plugins/stopped_goal_checker.cpp).
For a future physical docking/gripper stage, restore a deliberate docking-heading
contract; the current orientation-free setting is for logical payload placement.

## Install And Run

Use Ubuntu 24.04 / WSL with ROS 2 Jazzy installed as described in the README.
From the repository root:

```bash
sudo apt update
sudo apt install -y ros-jazzy-navigation2 ros-jazzy-nav2-bringup \
  ros-jazzy-nav2-regulated-pure-pursuit-controller ros-jazzy-nav2-smac-planner \
  ros-jazzy-robot-state-publisher \
  ros-jazzy-xacro ros-jazzy-ros-gz ros-jazzy-cv-bridge ros-jazzy-tf2-tools \
  python3-colcon-common-extensions python3-rosdep
source /opt/ros/jazzy/setup.bash
# Only if rosdep has not previously been initialized:
sudo rosdep init
rosdep update
cd ros2_ws
rosdep install --from-paths src --ignore-src -r -y
cd ..
TRANSPORT_MODE=amr VISION_SOURCE=gazebo bash run_ubuntu.sh
```

Open `http://127.0.0.1:8000`, wait for **AMR ready**, add one product and press
Start. The launcher generates the map, builds the AMR package, starts the normal
factory/camera stack, and launches exactly one robot/Nav2 stack. Do not launch
another copy manually at the same time. Logs include `logs/amr.log` and the
existing backend/Gazebo/camera logs. Ctrl+C stops the launcher.

No Nav2 installation is needed for existing modes:

```bash
TRANSPORT_MODE=simulated VISION_SOURCE=synthetic bash run_ubuntu.sh
# Browser only, with no ROS/Gazebo launch:
TRANSPORT_MODE=simulated VISION_SOURCE=synthetic .venv-wsl/bin/python scripts/run_factory.py
```

PowerShell: `./run_powershell.ps1` continues using simulated transport by default.
AMR mode explicitly refuses missing navigation dependencies; it never silently
substitutes simulated delivery. `VISION_SOURCE` remains independently selectable.

## Verify

Normal tests do not require ROS:

```bash
env -u PYTHONPATH .venv-wsl/bin/python -m pytest
.venv-wsl/bin/python -m ruff check .
.venv-wsl/bin/python -m ruff format --check .
.venv-wsl/bin/python scripts/check_integrations.py
```

Clearing `PYTHONPATH` for pytest prevents an already-sourced ROS installation
from injecting its optional launch-testing plugins into the isolated test venv.
In a clean Python-only shell, `python -m pytest` works normally.

In a second Ubuntu terminal while the AMR launcher is running:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
ros2 node list
ros2 topic list
ros2 action list
ros2 topic echo /scan --once --field ranges
ros2 topic echo /odom --once
ros2 run tf2_tools view_frames
python3 scripts/check_amr_pipeline.py
ros2 topic echo /reconfactory/amr/status
```

Before starting production, verify three named destinations with real Nav2 goals:

```bash
python3 scripts/check_amr_pipeline.py --plan-all --goals home input_queue vision --timeout 100
```

The verifier checks finite LiDAR returns, odometry, a complete TF chain, the
action server, actual successful action results, final map-position error and
stopped-arrival odometry. It also prints per-goal elapsed time.
The all-pairs planning check also bounds transfer path lengths to detect a
regression back to long perimeter detours.
Never send these manual goals while a factory transport is active.

A repeatable, bounded full-stack test with its own port, database, ROS domain
73 and Gazebo partition is available. It shuts down its test processes afterward:

```bash
source /opt/ros/jazzy/setup.bash
.venv-wsl/bin/python scripts/run_amr_smoke.py
# Repeat production after the separate named-goal checks have passed:
.venv-wsl/bin/python scripts/run_amr_smoke.py --factory-only
# Separate isolated run with Nav2 disabled, verifying manual /cmd_vel:
.venv-wsl/bin/python scripts/run_amr_smoke.py --manual-drive
# Shorter camera/payload regression with real robot pickup and delivery:
.venv-wsl/bin/python scripts/run_amr_smoke.py --vision-only
# Isolated navigation regression without creating a product:
.venv-wsl/bin/python scripts/run_amr_smoke.py --navigation-only reject_output --goal-timeout 240
```

It runs the normal launcher headlessly, navigates named poses, then adds a normal
red product and checks that successful robot deliveries lead to completion.
Evidence and diagnostics are in `logs/amr_smoke/`. Headless Gazebo still needs a
working graphics/rendering environment for GPU LiDAR and the factory camera.

### Manual Drive Check Without Nav2

Stop production and its launcher first. Terminal 1:

```bash
source /opt/ros/jazzy/setup.bash
python3 scripts/generate_amr_map.py
gz sim -r data/amr/factory.world.sdf
```

Terminal 2:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
ros2 launch reconfactory_amr amr_navigation.launch.py enable_nav2:=false
```

Terminal 3, after sourcing Jazzy: `python3 scripts/check_amr_pipeline.py --manual-drive`.
It sends a short conservative `/cmd_vel` command, then zero velocity and checks
that odometry actually changed. This multi-terminal path is for debugging only;
normal AMR production remains one launcher command.

## Task Contract And Failures

Example (coordinates are looked up by name, never embedded in the task):

```json
{"task_id":"T-demo","product_id":"P-00001","origin":"input_queue","destination":"vision"}
```

Status adds `robot_id`, `status`, `phase`, `requested_at`, `started_at`,
`completed_at`, `navigation_time_s`, `failure_reason` and `cancel_requested`.
`accepted -> navigating (pickup) -> navigating (delivery) -> delivered` is the
successful sequence. Abort, rejection and cancellation never report delivery.
Navigation time measures wall time over pickup and delivery. The existing SQLite
event log stores this metadata; no schema migration is needed.

The backend requires a fresh readiness heartbeat. Heartbeat loss (10 s) or the
transport deadline plus 60 s of cancellation grace marks failure. The manager
requests cancellation after `AMR_TASK_TIMEOUT_S` (default 300 s), on backend loss,
Reset, Pause, emergency stop, or a cancelled task. Set this positive, finite
environment value on the launcher to adjust it for slower rendering hardware.
The task budget covers both pickup and delivery; no timeout reports success. Nav2
velocity smoothing stops stale upstream commands while the smoother and bridge
are alive. A whole bridge/smoother crash is not a hardware emergency stop; stop
Gazebo as well. Factory station faults still
use capability-based rerouting before dispatch; a fault at an active delivery
destination cancels that transport instead of claiming a successful handoff.

**Milestone limitation:** failed/cancelled transports keep the product and robot
payload in a conservative held state and block further transport until an explicit
factory Reset. Inspect the payload before Reset; no automatic recovery/retry of
a partly delivered load is implemented. Pause during active AMR transport means
cancel, not automatic action resumption. Simulated mode retains its existing
Pause/Resume and recovery behavior. Restarting the AMR manager during a task fails
the task rather than replaying it. Navigation tasks are not restored after a
whole backend restart; SQLite events retain the audit history.

## RViz And Limitations

```bash
rviz2 -d ros2_ws/src/reconfactory_amr/rviz/amr_navigation.rviz
```

The optional config includes Map, RobotModel, LaserScan, TF, global path, the
controller's local reference path (`/received_global_plan`) and costmaps.
The existing camera debug image remains
available in the vision RViz config or rqt_image_view. RViz is not required.

This is a simulation prototype, not a safety-certified robot controller. One AMR
and one logical payload are supported. The map is a conservative 2D approximation;
loading/unloading is logical, and payload pose updates use the existing Gazebo
service bridge rather than physical attachment. Payload positioning uses the
map-localized robot pose, so small localization offsets can be visible. Wheel slip/localization and
rendering load can affect navigation. The ROS-free suite passes on Windows and
Ubuntu and covers the browser-mode code used in Docker; container deployment
itself and GPU/container Nav2 operation need separate verification.

For a concise portfolio recording see [Demo Scenarios](DEMO_SCENARIOS.md).
