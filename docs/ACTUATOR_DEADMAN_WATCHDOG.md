# Gazebo Actuator Deadman Watchdog

This is simulation-level command protection, not certified functional safety or
a physical emergency stop. It adds a downstream layer to the existing ROS motion
supervisor without replacing Nav2, DiffDrive, factory scheduling or payload ownership.

## Why It Exists

The October 17 gate-death experiment left the AMR moving at approximately 0.45 m/s
after 1.5 seconds. Gazebo Harmonic DiffDrive retained its last command. That is
historical continued-motion evidence, not a measured baseline stopping time.

## Command Architecture

```text
Nav2 -> velocity_smoother -> ROS safety supervisor -> ROS /cmd_vel
  -> ros_gz_bridge -> Gazebo /amr/cmd_vel_requested
  -> C++ ActuatorWatchdog -> Gazebo /amr/actuator_cmd_vel
  -> unchanged DiffDrive -> wheel joints -> /amr/odom
```

The bridge does not publish the actuator topic. The model loads the watchdog as
a Gazebo Sim 8 system. If it fails to load, there is no direct fallback command
path to DiffDrive. The manager requires fresh ARMED status or STARTUP_INHIBITED
status with `startup_ready=true` before motion authorization. Plugin state is
separate from ROS safety state.

Implementation follows the [Sim 8 system plugin interfaces](https://gazebosim.org/api/sim/8/createsystemplugins.html)
and the installed headers. The [DiffDrive implementation](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/diff_drive/DiffDrive.cc)
remains unchanged. `Configure` establishes transport; `PreUpdate` publishes
validated or zero commands; `Reset` latches simulation reset. A pure C++ policy
with injected monotonic times is tested without a running simulator.

## Timing And States

Model settings in `ros2_ws/src/reconfactory_amr/urdf/amr.urdf.xacro`:

| Setting | Default |
|---|---:|
| Command timeout | 0.30 s |
| Output period | 0.02 s |
| Startup fresh-zero confirmation | 0.30 s |
| Odometry freshness | 0.50 s |
| Stable stopped interval | 0.30 s |
| Stopped linear / angular thresholds | 0.03 m/s / 0.05 rad/s |

These are engineering parameters, not guaranteed real-time deadlines. All numeric
thresholds must be finite and positive; output period must be below command timeout.
Automatic timeout reset is deliberately unsupported. Invalid configuration latches
and cannot be cleared by the reset service.

- `STARTUP_INHIBITED`: repeatedly outputs zero. A continuous fresh zero-input
  stream and fresh stable stopped odometry set `startup_ready`. Only a subsequent
  fresh nonzero command transitions to ARMED. Initialization gaps clear readiness
  without latching a robot that has never been armed. They never permit motion.
- `ARMED`: forwards only the latest finite command. Fresh zero commands remain
  valid during waiting, cancellation and charging. Missing commands, invalid
  commands or a simulation pause/reset fault-latch the plugin.
  An armed robot remains subject to the timeout even while its commands are zero;
  it never automatically returns to startup initialization.
- `FAULT_LATCHED`: repeatedly outputs zero, including after ROS gate restart.
  Explicit validated reset returns to STARTUP_INHIBITED, never directly to motion.

Time is sampled from `steady_clock` under the policy mutex, shared with transport
callbacks. A late command cannot conceal an expiry between update callbacks.
Commands received while inhibited are discarded rather than queued for replay.
Simulation time is not used for freshness. Pausing after arming latches; initial
paused startup cannot arm. Resume requires fresh stopped evidence. Negative time
jumps and world reset latch. Pausing physics is not evidence of a physical stop.

The asynchronous Gazebo transport hop to DiffDrive introduces update/callback
latency; zero publication alone is not a stop claim. Live tests measure actuator
zero arrival and stable odometry separately. A frozen Gazebo process cannot run
this watchdog; there is no protection outside the simulator process.

## Build And Run

After the README's Jazzy/Nav2 setup, install build dependencies:

```bash
sudo apt install -y build-essential cmake ros-jazzy-ament-cmake \
  ros-jazzy-ament-cmake-gtest ros-jazzy-gz-sim-vendor \
  ros-jazzy-gz-transport-vendor ros-jazzy-gz-plugin-vendor nlohmann-json3-dev
source /opt/ros/jazzy/setup.bash
TRANSPORT_MODE=amr bash run_ubuntu.sh
```

The launcher builds the package and sources its environment hook **before** starting
Gazebo. The hook adds the installed library directory to `GZ_SIM_SYSTEM_PLUGIN_PATH`.
No manual library copying is required. Browser-only Windows/Docker do not build or
load this plugin.

## Observe

From the repository root in another sourced terminal:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
ros2 topic info /cmd_vel -v
gz topic -i -t /amr/cmd_vel_requested
gz topic -i -t /amr/actuator_cmd_vel
ros2 topic echo /reconfactory/amr/actuator/state
```

Expected topology: one ROS final publisher (`reconfactory_amr_safety`), one bridge
publisher on the Gazebo request topic, one Gazebo publisher on the actuator topic.
The actuator publisher's Gazebo address matches the request subscriber, not the
bridge's publisher address. ROS inspection alone cannot establish this ownership.

`/amr/actuator_watchdog/state` is Gazebo StringMsg JSON, bridged to ROS String on
`/reconfactory/amr/actuator/state`. Actuator commands are bridged GZ_TO_ROS only on
`/reconfactory/amr/actuator/command` for measurement. The observer never publishes
velocity. Its background HTTP worker posts to `/api/transport/actuator`.

The dashboard distinguishes ROS SAFETY from GAZEBO ACTUATOR. Backend observations
expire after one second; stale messages cannot claim stopping. Sample sequences
prevent repeated identical observations from refreshing freshness. SQLite records
transition events using stable instance/sequence IDs, not events every physics tick.
The plugin repeats a bounded 64-event history; long outages can lose older audit
events. Neither database nor HTTP access occurs in the plugin.

## Explicit Recovery

First inspect the robot and payload. Restore the ROS gate/manager, let Nav2 cancel,
and reconcile the old task. In the demo, dashboard **Reset** deliberately aborts
the old production run; it does not count the retained product as delivered.

If ROS safety is also FAULT_LATCHED, reset that layer first:

```bash
ros2 service call /reconfactory/amr/safety/reset std_srvs/srv/Trigger '{}'
```

Then explicitly reset the Gazebo layer:

```bash
ros2 service call /reconfactory/amr/actuator/reset std_srvs/srv/Trigger '{}'
```

For manager/backend failures, inspect both layers as well: an additional command
gap can latch the actuator even when the original injected failure was not gate
death. Reset each latched layer in the order above; a successful ROS reset alone
does not clear an actuator latch. The isolated harness now verifies both observed
states and fresh actuator readiness before declaring its explicit recovery done.

The ROS operator service requires a fresh DISARMED gate, reset-eligible DISARMED
manager lease, idle backend with no task/emergency, no active observed NavigateToPose
goal, and fresh stable stopped odometry. The plugin independently requires its
latched state, fresh continuous zero input, fresh stable stopped odometry and an
explicit request. It does **not** validate factory ownership itself. After reset,
new zero initialization is required and the normal ROS mission lease still gates
all movement. There is no automatic recovery loop.

The underlying `/amr/actuator_watchdog/reset` Gazebo Boolean service is a trusted
internal interface, not an authenticated security boundary. Do not call it to
bypass operator reconciliation. Other arbitrary Gazebo publishers can also bypass
topic ownership; DDS/Gazebo access control is outside this milestone.

## Reproduce Verification

Stop the regular demo first. Tests use domain 73, a unique Gazebo partition and
database, and signal only their owned stack:

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build --symlink-install
colcon test --packages-select reconfactory_gazebo_watchdog
colcon test-result --verbose
source install/setup.bash
cd ..
python3 scripts/run_safety_campaign.py --manager-trials 1 --gate-trials 3
# Or run individual scenarios:
python3 scripts/run_amr_smoke.py --safety gate-crash
python3 scripts/run_amr_smoke.py --safety gate-crash
python3 scripts/run_amr_smoke.py --safety gate-crash
python3 scripts/run_amr_smoke.py --safety manager-crash
python3 scripts/run_amr_smoke.py --safety backend-outage
python3 scripts/run_amr_smoke.py --fault-replan
python3 scripts/run_amr_smoke.py --energy
python3 scripts/run_amr_smoke.py --factory-only
.venv-wsl/bin/python -m pytest
.venv-wsl/bin/python -m ruff check .
.venv-wsl/bin/python -m ruff format --check .
node tests/frontend_movement.test.js
```

Gate-crash assertions require automatic actuator zero, stable stop, latched fault,
retained payload/no false delivery, no automatic restart motion, invalid-reset
rejection and a new delivered mission after explicit recovery. There is no test
cleanup velocity publisher. JSON traces under `logs/amr_smoke/safety_*.json` retain
failed trials as well as successful ones. Timing starts at signal dispatch; stopping
distance is integrated odometry translation, not commanded speed times duration.

The campaign archives per-trial logs and reports successful-run median/worst
latencies and distances separately from failures. Measurement times include ROS
bridge and verifier sampling latency; `command_age_at_timeout_ms` is measured by
the plugin's own steady clock. Physical stop includes a 0.30-second stationary
confirmation window. Historical continued motion is not a precise old stopping
time or a certified comparison baseline.

## Implementation Files

Added:

- `ros2_ws/src/reconfactory_gazebo_watchdog/`: CMake/package metadata, plugin-path
  environment hook, `Policy.hh`, `ActuatorWatchdog.cc`, and `policy_test.cc`.
- `ros2_ws/src/reconfactory_amr/reconfactory_amr/actuator_observer.py`: observation
  forwarding and explicit operator recovery, with no velocity publisher.
- `ros2_ws/src/reconfactory_amr/reconfactory_amr/backend.py`: bounded HTTP worker
  keeping manager status/lease callbacks independent of network and SQLite delays.
- `reconfactory/actuator_watchdog.py`: ROS-independent validation/recovery contracts.
- `tests/test_actuator_watchdog.py`, `tests/test_amr_backend.py` and this document.

Modified integration surfaces:

- AMR bridge YAML, Xacro, launch, package/setup metadata and manager readiness.
- AMR navigation request classification: known unsubmitted tasks wait when
  readiness disappears; uncertain restarted tasks still fail closed. Targeted
  transport tests cover this distinction. Cancellation logs include safety ages.
- `run_ubuntu.sh` and `scripts/run_amr.sh`: build/load before Gazebo startup.
- `reconfactory/amr_transport.py`, `app/main.py`, `frontend/app.js` and
  `frontend/index.html`: separate expiring actuator observations and audit events.
- `scripts/check_amr_pipeline.py`, `scripts/check_amr_safety.py`,
  `scripts/run_amr_smoke.py`, `scripts/run_safety_campaign.py`: live verification.
- API/browser tests and `.github/workflows/tests.yml`: regression and pure C++ CI.
- README and architecture, ROS, Gazebo, AMR navigation/safety, charging, replanning,
  demo and API documentation. Existing Nav2 tuning, DiffDrive geometry, factory
  scheduling and ROS safety-policy checks are unchanged.

## Verification Record

The [24–25 October workspace recovery record](RECOVERY_VERIFICATION_2026-10-24.md)
records 367 passing Python tests on Windows and Ubuntu, the clean Sim 8.15.0
build, all 24 policy cases and 20 browser scenarios, and three complete passing
gate-crash trials (stable stops 0.750–0.761 seconds). Manager loss, backend outage,
replanning, charging and camera-backed normal production also passed. It includes
failed attempts and the station-snapshot transaction fix. The historical
October 23 observations below are retained for comparison.

The interrupted October 23 campaign's first two independent gate-crash
trials passed the full stop, latch, invalid-reset, explicit-recovery and new-delivery
sequence. Stable stops were observed at 0.795 and 0.797 seconds, with approximately
0.1125 m travel each. Remaining campaign outcomes are not yet claimed.

The campaign also passed fault-aware replanning through real camera inspection
and Accepted output. It encountered an AMCL startup timeout, a pre-submission
task-ownership race (fixed), and intermittent ROS authorization/command timeouts.
A separate charging retry observed a real actuator command gap of 307 ms and
correctly latched rather than continuing motion. That campaign did not fully
verify charging and normal-production compatibility. Its final
normal-production trial was interrupted after a ROS authorization latch; it is
not a successful test. No safety timeout was relaxed to hide these failures.

Detailed cancellation logging subsequently captured 0.913-second-old ROS safety
and actuator observations while the manager was doing synchronous HTTP work. HTTP
is now isolated in a bounded worker: ROS callbacks never wait for it, observations
retain their actual response receipt times, stale backend authorization still
fails closed at 0.6 seconds, and failed status posts retain order for retry. Queue
overflow makes authorization unavailable until restart. The safety gate's command,
heartbeat and odometry limits and the Gazebo watchdog's 0.30-second limit are
unchanged. Its interrupted live verification was completed during the later
workspace recovery, after also batching SQLite station snapshots to reduce
synchronous backend disk stalls.

Earlier attempts exposed a timestamp sampled before mutex acquisition (fixed by
sampling inside the lock), startup arming before any movement request (changed to
fresh zero readiness followed by explicit fresh movement), and a verifier that
misread protobuf's omitted default `false` service response. These failed attempts
are retained locally under `logs/amr_smoke` and the earlier campaign directory;
they are not counted as successful acceptance trials.

Known limits: one trusted robot/transport graph; in-memory latch lost with a whole
Gazebo restart; no real-time scheduling or hardware braking guarantee; no recovery
of missions after backend reset. Standalone external Nav2 behavior actions are not
part of the supported single-manager ownership model. Independent real actuator
protection is still necessary on a physical robot.
