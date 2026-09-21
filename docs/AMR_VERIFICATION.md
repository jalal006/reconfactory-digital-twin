# AMR Milestone Verification

Verification dates: 2026-09-14 through 2026-09-21. The latest controller checks
are below; older measurements are retained as historical comparisons.
This is a single-robot simulation prototype, not
a production fleet or safety controller. Run instructions, contracts, TF,
configuration and limitations are in [AMR Navigation](AMR_NAVIGATION.md).

## September 21 Navigation Update

Replaced MPPI plus Rotation Shim with Nav2 Regulated Pure Pursuit. The global
planner is unchanged; its final orientation now follows the approach path.
Collision prediction, obstacle costmaps and stopped-arrival checks remain enabled.
Also increased the BT action acknowledgement budget from 20 to 1,000 ms after
a live test aborted a valid path due to a delayed planner acknowledgement.

The live verifier now integrates absolute odometry heading changes (including
wraparound) and rejects a transfer exceeding 360 degrees of total rotation.
Successful arrival alone is no longer enough to pass. Six consecutive goals
passed in the real isolated Gazebo/Nav2 stack:

| Destination | Time | Total Turning | Driven Distance |
|---|---:|---:|---:|
| Vision (from Home) | 8.6 s | 27 deg | 2.84 m |
| Processing A | 8.5 s | 94 deg | 2.30 m |
| Quality | 8.8 s | 96 deg | 2.24 m |
| Processing B (reverse direction) | 11.5 s | 205 deg | 2.43 m |
| Quality | 11.6 s | 191 deg | 2.43 m |
| Rejected | 9.9 s | 116 deg | 2.59 m |

No full spins occurred in this sequence. The roughly 180-degree changes for
opposite-direction transfers are necessary direction changes, not full laps.
Map arrival error was 0.11-0.12 m and measured arrival speeds met the stopped
thresholds. All 56 directed station pairs also passed planning checks. These
are measured samples, not a guarantee under every load or obstacle arrangement.

Regression results: **183 tests pass on Windows and Ubuntu/WSL**, Ruff lint
passes, and all 84 Python files pass formatting checks.

A separate `--factory-only` run completed the normal red product in **54.2 s**
from creation to completion (startup excluded). All four delivery events came
from Nav2 success, and Vision used five real frames with `method=gazebo_camera`.
Transport durations including pickup were 16.03 s (Input -> Vision), 11.17 s
(Vision -> Processing A), 11.63 s (Processing A -> Quality), and 9.79 s
(Quality -> Accepted). The product ended `completed` / `accepted` at
`accepted_output`. This full-cycle run validates the perception/delivery path;
the six-goal run above separately measures cumulative turning.

The AMR package rebuilt successfully through the normal launcher. Dependency
checks found the new controller, ROS/Gazebo, camera bridge and Nav2 installed;
launcher syntax and whitespace checks passed. Both isolated test stacks stopped
their services, confirmed by a process-list check.

## Earlier Milestone Checks

- Python: 179 tests passed on both Windows and Ubuntu/WSL, including all 132 original
  regressions. Tests remain independent of ROS/Gazebo/Nav2.
- JavaScript: nine movement scenarios passed using the V8 test harness.
- Both ROS packages built successfully with `colcon build --symlink-install`.
- Integration checker found ROS 2 Jazzy, Gazebo, ros_gz_bridge, cv_bridge and Nav2.
- Live headless Gazebo: finite LiDAR returns, odometry, complete map-to-laser TF,
  and the NavigateToPose action server verified.
- Nav2 planned all 56 directed station pairs on the generated occupancy map.
  Planning success is not presented as evidence of physically driving all pairs.
- Real navigation to Home, Input and Vision succeeded, with map-position error
  within 0.15 m in the recorded checks.
- The separate Quality -> Accepted -> Rejected navigation run passed, with
  final map-position errors of 0.09 m, 0.12 m and 0.05 m respectively.
- Ruff lint and format checks passed (83 Python files); the nine browser
  movement scenarios were also rerun successfully after the navigation changes.
- The camera checker received 128 real RGB images in ten seconds at 640x480;
  no duplicate factory ROS nodes were present. The loaded product's inspection
  used `gazebo_camera`, not the timeout fallback.
  One initial three-second sample received no frames; use a longer sampling
  window to allow ROS discovery and camera startup before diagnosing failure.
- Manual driving with Nav2 disabled passed: linear commands changed odometry,
  angular commands changed yaw, and LiDAR/TF remained available.
- Full loaded production passed through the normal launcher: Input -> Vision ->
  Processing A -> Quality -> Accepted. The supervisor finished the normal red
  product with `status=completed`, `quality=accepted`, and
  `current_location=accepted_output`, after four successful Nav2 transports.
  Real five-frame camera inspection passed with `method=gazebo_camera`.
- Launcher shell syntax and `git diff --check` passed. The isolated smoke runner
  stopped its test stack after completion.

## Full Production Result

Command: `.venv-wsl/bin/python scripts/run_amr_smoke.py --factory-only` after
sourcing ROS 2 Jazzy. After the AMR-only layout optimization, the recorded cycle
took approximately **2 minutes 41 seconds**, versus **5 minutes 35 seconds** in
the previous conveyor-constrained layout. Subsequent orientation-free,
stopped-arrival tuning completed the same cycle in **1 minute 59 seconds**, about
26% faster than the expanded-layout baseline on this WSL machine. Startup/build
time is excluded. Transport times include pickup and delivery, not just driving
with cargo:

| Transfer | Previous | Expanded Workcells | Stopped-Arrival Tuning |
|---|---:|---:|---:|
| Input -> Vision | 69.63 s | 56.53 s | 33.04 s |
| Vision -> Processing A | 66.36 s | 34.70 s | 41.31 s |
| Processing A -> Quality | 124.39 s | 30.61 s | 12.97 s |
| Quality -> Accepted | 67.35 s | 33.31 s | 24.51 s |

The last tuning removes unnecessary final-heading turns, not positional arrival
requirements: Nav2 still requires current position within 0.12 m, translational
speed <= 0.05 m/s and angular speed <= 0.1 rad/s. Maximum cruising speed remains
0.45 m/s. The first stable-endpoint tuned run was faster overall, but not every
leg was faster; these are samples, not a guaranteed optimum or endurance result.
An earlier trial with changing final-approach orientation retriggered Rotation
Shim on replans and was stopped. It was disabled in that historical profile;
the current Pure Pursuit controller has no Rotation Shim wrapper.
A separate travel-bearing/terminal-angle guidance experiment completed in 2:29,
so it was not retained. The 1:59 profile was subsequently replaced on September 21.

With that earlier profile, an isolated six-goal sequence also passed:
Vision -> Processing A -> Quality -> Processing B -> Quality -> Rejected.
Reported map errors were 0.02-0.12 m; arrival odometry met the stopped thresholds
(linear <= 0.05 m/s, angular <= 0.1 rad/s). Per-goal times ranged from 14.7 to
37.1 seconds. Some controller settling/turning remains, particularly when
reversing travel direction; these measurements do not establish optimal or
identical timing on every run.

The new 13 x 9 m world places workcells around a clear central transport aisle.
The actual Nav2 planner produced a 2.48 m path from Processing A to Quality
(2.20 m straight-line distance), and a 2.75 m path from Processing B to Quality
(2.61 m straight-line distance). All 56 directed station pairs planned; the
verifier rejects long detours on the main transfers. Maximum commanded speed is
0.45 m/s, up from 0.25 m/s, with matching smoother/drive limits. Collision radius,
costmap obstacle checks, localization ownership and delivery gating are retained.
The relocated Vision camera again passed the normal red product using five real
rendered frames. These are measured single-run results, not timing guarantees.

A subsequent isolated `--navigation-only station_b quality reject_output` run
also passed actual driving, with final map-position errors of 0.05 m, 0.06 m and
0.12 m. Open-aisle commands reached 0.426 m/s. Both optimized-layout test stacks
shut down normally after completion.

All four transports finished below the default 300 s task budget. The final
product had completed visual inspection, drilling and quality check. This is one
verified full-cycle run, not an endurance/reliability certification. The live
station-fault combinations and all three loaded recipes still need a broader
Gazebo soak test; they are covered by the ROS-free state-machine tests.

## Runtime Scope

The smoke runner uses the actual Ubuntu launcher, a separate port and database,
ROS domain 73, a unique Gazebo partition, and process-group cleanup. It does not
teleport the robot or fabricate Nav2 success. During the initial milestone,
loaded trials revealed a
legacy-cart LiDAR obstruction and insufficient service-aisle clearance; these
were corrected in the AMR-specific model/world/map.
Further trials caught fence-corner collisions. The local costmap now includes
the static map, and global path costs favor additional tracking clearance;
collision detection has not been disabled. Failed trials correctly paused the
product at its last confirmed station rather than reporting a delivery.
Persistent pure-pursuit corner failures prompted a switch to the standard Jazzy
MPPI controller, with circular-radius collision checking and conservative motion
limits. The full-cycle outcome above was measured, not inferred from planning.
Runtime diagnostics then exposed a low-speed docking dead zone; path-angle and
goal-angle thresholds now match position tolerance. A later loaded run reached
Processing A but hit the old 180 s transport budget while still moving toward
Quality. The configurable task budget now defaults to 300 s; the independent
10 s heartbeat-loss watchdog remains unchanged.

Later diagnostics separated AMCL's LiDAR-visible map from the conservative
navigation map: invisible collision envelopes and floor-edge boundaries must
not be interpreted as sensor-visible walls. Rotation Shim now uses
`rotate_to_heading_once: true`; rotating after every path refresh caused repeated
stops. The subsequent three-goal run reached Quality and both output bins.

`rosdep install --from-paths src --ignore-src -r -y` was attempted but blocked
because rosdep has not been initialized on this machine. Required runtime
packages were already installed and the workspace built. The initialization
commands are documented; no success is claimed for rosdep installation.

RViz GUI appearance, interactive Gazebo GUI appearance, fresh OS installation,
Docker GPU/Nav2 deployment, and every physical fault/recovery combination have
not been exhaustively tested. Fault, cancellation, duplicate/stale result,
multi-product reservation and recipe cases have deterministic unit coverage.
Transport cancellation/failure requires inspection and Reset in this milestone.

## Added Files

```text
docs/AMR_NAVIGATION.md
docs/AMR_VERIFICATION.md
reconfactory/amr_transport.py
reconfactory/transport.py
scripts/check_amr_pipeline.py
scripts/generate_amr_map.py
scripts/run_amr.sh
scripts/run_amr_smoke.py
tests/test_amr_transport.py
ros2_ws/src/reconfactory_amr/package.xml
ros2_ws/src/reconfactory_amr/setup.py
ros2_ws/src/reconfactory_amr/setup.cfg
ros2_ws/src/reconfactory_amr/resource/reconfactory_amr
ros2_ws/src/reconfactory_amr/reconfactory_amr/__init__.py
ros2_ws/src/reconfactory_amr/reconfactory_amr/manager.py
ros2_ws/src/reconfactory_amr/reconfactory_amr/navigation.py
ros2_ws/src/reconfactory_amr/launch/amr_navigation.launch.py
ros2_ws/src/reconfactory_amr/config/bridge.yaml
ros2_ws/src/reconfactory_amr/config/nav2.yaml
ros2_ws/src/reconfactory_amr/config/stations.yaml
ros2_ws/src/reconfactory_amr/config/factory_layout.yaml
ros2_ws/src/reconfactory_amr/maps/reconfactory_map.yaml
ros2_ws/src/reconfactory_amr/maps/reconfactory_map.pgm
ros2_ws/src/reconfactory_amr/maps/reconfactory_lidar_map.yaml
ros2_ws/src/reconfactory_amr/maps/reconfactory_lidar_map.pgm
ros2_ws/src/reconfactory_amr/urdf/amr.urdf.xacro
ros2_ws/src/reconfactory_amr/rviz/amr_navigation.rviz
```

The empty `resource/reconfactory_amr` file is a required ament package-index
marker, not unused content. Generated runtime worlds, databases, logs, build and
install directories remain ignored by Git.

## Modified Files

```text
README.md
analytics/metrics.py
app/main.py
docs/architecture.md
docs/ROS2_INTEGRATION.md
docs/GAZEBO_FALLBACK.md
docs/DEMO_SCENARIOS.md
frontend/app.js
frontend/index.html
gazebo_fallback/scripts/sync_backend_to_gazebo.py
integrations/detector.py
reconfactory/scheduler.py
reconfactory/supervisor.py
run_ubuntu.sh
tests/frontend_movement.test.js
tests/test_analytics.py
tests/test_gazebo_sync.py
```

## Test Coverage Added

Contracts validate station lookup, malformed requests, JSON serialization,
duplicate/busy tasks, legal transitions and cancellation races. A mocked Nav2
client tests pickup-before-delivery, rejection, unavailable server, abort and
cancellation. Supervisor tests exercise all three recipes and defects, no arrival
before delivery, terminal output gating, lost heartbeat, unavailable transport,
drill rerouting and nine products without station sharing. Gazebo tests cover
single payload-pose authority, cargo geometry, actual SDF surface height and
reset. Browser tests prevent predicted AMR arrivals and recovery-buffer jumps.
Offline analytics is checked under AMR/Gazebo environment settings.
Navigation configuration tests check both costmaps, payload footprint clearance,
consistent inflation parameters and all docking poses against world obstacles.
Layout regressions check direct transfer corridors with clearance beyond the
robot radius, the relocated camera sensor, unchanged original conveyor world,
updated cargo surface coordinates and consistent controller/smoother/drive limits.
Stopped docking, approach-heading planning, collision checking and action
acknowledgement timeout have configuration regressions. Motion trace tests check
heading wraparound, full-turn accumulation and invalid/duplicate samples. The
live verifier checks arrival odometry and total turning as well as action success
and position.

## Portfolio Demo

Use the [45-60 second recording outline](DEMO_SCENARIOS.md#amr-portfolio-demo-45-60-seconds).
Show the robot carrying one product, the live task status, camera inspection,
and processing starting after delivery. Use labeled edits for the full cycle;
conservative navigation around the existing equipment takes several minutes.
