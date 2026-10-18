# Independent AMR Motion Supervisor

This is ROS 2 supervisory command inhibition for a simulated robot, **not a
hardware emergency stop or certified industrial functional safety**. It makes no
claim of compliance with ISO 13849, IEC 61508 or ISO 3691-4.

## Why A Separate Process

Previously, an AMR manager crash could leave an active Nav2 goal driving the
robot until a restarted manager discovered and cancelled it. Historical observed
stops took approximately 4.29-5.87 seconds; those were observations, not bounds.
Cancelling in the manager cannot protect against that same manager being dead.

The new process keeps a local watchdog and publishes repeated zero commands
without waiting for a manager restart, backend request, database write or action
cancellation. The factory supervisor still owns production and delivery state.

```text
FactorySupervisor -- current task --> AMR Manager -- NavigateToPose --> Nav2
                                         |
                                  fresh mission lease
                                         v
Nav2 controller/behaviors -> cmd_vel_nav -> velocity_smoother
                                         |
                            /reconfactory/amr/nav_cmd_vel
                                         v
                             reconfactory_amr_safety <--- /odom
                                         |
                                      /cmd_vel
                                         v
                           ROS-Gazebo bridge -> /amr/cmd_vel -> DiffDrive
```

The safety node is the only intended final `/cmd_vel` publisher in normal launch.
No custom planner, alternate charging velocity path or new production scheduler
is introduced. The existing camera, smoothing, AMCL and TF ownership are unchanged.

## States And Freshness

| State | Output | Exit |
|---|---|---|
| `DISARMED` | Repeated zero | Fresh valid mission lease |
| `AUTHORIZED` | Only finite, locally fresh Twist | Hold/disarm, or fault |
| `CONTROLLED_HOLD` | Repeated zero | Fresh valid mission lease |
| `FAULT_LATCHED` | Repeated zero | Explicit eligible reset to DISARMED only |

Authorization requires the manager's recently checked backend task to agree with
its navigating task, no cancellation/emergency, and certain ownership. Backend
checks are eligible for 0.6 seconds; HTTP calls have a 0.5-second timeout. A steady
timer sends a lease every 0.1 seconds. A blocked or crashed manager therefore
cannot renew the independent watchdog indefinitely.

Readiness also requires the gate's own `odometry_fresh` report, not merely an
available Nav2 action server or odometry received by some other node. Both the
production manager and isolated diagnostic driver wait for this evidence before
granting authorization. No startup grace bypasses odometry protection.

Leases contain `session_id`, increasing `sequence`, `mode`, `task_id`,
`mission_type`, `reset_eligible` and `reason`. The task authorization token is
`<factory task ID>:<pickup/delivery phase>:<navigation generation>`. This prevents
pickup authorization from silently carrying over to delivery or a replacement.
Production, charging and isolated diagnostics use the same policy.

Duplicate sequence numbers do not refresh freshness. Retired sessions/tasks cannot
reauthorize; a session change during authorized motion latches. Changing a task
without a controlled hold, or changing the mission type under its token, latches.
All transitions clear the previous command. Commands received while inhibited are
discarded, not buffered for recovery. DDS subscriptions keep only the latest item.

The gate uses its own `time.monotonic()` receipt times and a ROS **steady-clock**
timer, not simulation time or timestamps originating in another process.

Configuration: `ros2_ws/src/reconfactory_amr/config/safety.yaml`:

| Parameter | Default |
|---|---:|
| `lease_timeout_s` | 0.50 s |
| `command_timeout_s` | 0.30 s |
| `first_command_timeout_s` | 2.00 s |
| `odometry_timeout_s` | 0.50 s |
| `stopped_duration_s` | 0.30 s |
| `linear_stop_m_s` | 0.03 m/s |
| `angular_stop_rad_s` | 0.05 rad/s |

The initial command grace accommodates Nav2 planning but does **not** permit
motion before a fresh command arrives. Once a command has arrived, the shorter
command timeout applies. The independent output timer runs at 20 Hz. Values are
engineering settings, not guaranteed deadlines on a non-real-time OS.

Fresh odometry must remain below both speed thresholds for the full stable window.
A gap resets that window. Sending zero is not evidence of stopping; stale odometry
never confirms stopped. `physical_stop_after_inhibition_s` measures this stable
confirmation after the gate transition, not from an externally injected crash.

## Interfaces And Observation

| Interface | Type / Direction |
|---|---|
| `/reconfactory/amr/nav_cmd_vel` | Twist, smoother -> gate |
| `/reconfactory/amr/safety/lease` | JSON String, manager -> gate |
| `/reconfactory/amr/safety/state` | JSON String, gate -> observers, transient-local |
| `/cmd_vel` | Twist, gate -> existing robot bridge |
| `/odom` | Odometry, bridge -> gate |
| `/reconfactory/amr/safety/reset` | Trigger, explicit operator service |

State includes reason, current authorization token, mission type, heartbeat and
odometry ages, inhibited/stopped flags, last fault wall time and reset requirement.
The dashboard receives it through `transport.safety` in the existing HTTP/WebSocket
snapshot. Missing or older-than-1.5-second backend observations display UNAVAILABLE,
not an assumed stop. The display is observational and cannot authorize motion.

A bounded background worker posts state plus transition events to
`POST /api/transport/safety`. Network/database stalls never run in the gate's
control callback. SQLite uses existing event JSON, with deduplication by gate
instance/event sequence. Events cover authorization, hold, disarm, expiry, latch,
stop confirmation, reset request/rejection/completion. It does not store each
velocity sample. Queue capacity is finite; prolonged outages can lose old audit
events, without affecting command inhibition.

## Planned Changes And Recovery

Intentional pause, destination-fault cancellation and phase changes use
CONTROLLED_HOLD. Existing Nav2 cancellation acknowledgement plus stopped odometry
still precede a replacement. A fresh generation receives a fresh lease, so normal
fault replanning does not require operator reset. Charging navigation uses its own
task lease; stationary charging is inhibited until a new navigation is authorized.

Unexpected lease/backend/command/odometry loss latches. Manager restart alone does
not clear it. The manager attempts cancellation when available and preserves the
existing failed-task/payload semantics. A stop never counts as a delivery.

For an unexpected fault, first inspect the robot and retained payload. Restore the
backend/manager, let cancellation reconcile ownership, and keep production stopped.
For the simulation demo, the existing dashboard **Reset** aborts the old production
run and clears its products; it is not a delivery or an automatic continuation of
the held payload. Only after this deliberate reconciliation, request:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
ros2 service call /reconfactory/amr/safety/reset std_srvs/srv/Trigger '{}'
```

Reset requires a fresh DISARMED/reset-eligible manager lease, fresh stable stopped
odometry, an idle/certain manager, no active NavigateToPose goal, fresh idle backend
state and no unresolved emergency. Rejected calls leave the latch intact. Success
returns DISARMED, clears the old command, retires the old token and requires a new
mission. Do not repeatedly call Reset instead of resolving the stated condition.
This service is an operational acknowledgement, not authentication or a security
boundary.

## Run And Verify

Normal Ubuntu/WSL production remains one command from the repository:

```bash
TRANSPORT_MODE=amr bash run_ubuntu.sh
```

In another sourced terminal:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
ros2 topic info /cmd_vel -v
ros2 topic echo /reconfactory/amr/safety/state
# Run each continuous monitor separately; Ctrl+C ends it.
ros2 topic echo /reconfactory/amr/safety/lease
ros2 topic echo /odom
```

Expect one final publisher, `/reconfactory_amr_safety`. During valid motion the
state is AUTHORIZED; station waiting is inhibited. Browser-only/Windows mode needs
no ROS safety process.

Automated isolated checks create their own stack, database, ROS domain 73 and
Gazebo partition, then stop only their owned processes:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
python3 scripts/run_amr_smoke.py --safety manager-crash
python3 scripts/run_amr_smoke.py --safety backend-outage
python3 scripts/run_amr_smoke.py --safety gate-crash
python3 scripts/run_amr_smoke.py --fault-replan
python3 scripts/run_amr_smoke.py --energy
python3 scripts/run_safety_campaign.py
```

The campaign records three manager crashes, backend loss, gate death, fault
replanning, charging and an intentionally ungated historical-path comparison.
Results and every trial log are under `logs/safety_campaign_<timestamp>/`.
Per-crash traces are under `logs/amr_smoke/safety_*.json`.

The comparison restores smoother -> `/cmd_vel` and disables the gate **only** when
`--unsafe-baseline` is paired with the isolated manager-restart scenario. Both
launch and manager reject this mode outside domain 73 and a test Gazebo partition.
It is deliberately unsafe and must never be used for production. The same loaded
route, initial speed range and stopped thresholds are used for comparison.

For independent manual or named-goal diagnostics, use
`python3 scripts/run_amr_smoke.py --manual-drive` or
`python3 scripts/run_amr_smoke.py --navigation-only vision station_a quality`.
These explicitly disable the production manager and send short-lived diagnostic
leases. Manual velocity still enters the intermediate topic, never bypassing the
gate. Do not run diagnostic leases against an active production manager.

Failure measurements start at the test observer's signal dispatch, so they include
OS/DDS observation latency. Command inhibition, fault-state observation and fresh
stable odometry are measured separately. Physical stop must happen before manager
restart in the independent trials. The old path deliberately restarts the manager.
Trace reports include payload retention, false-delivery checks, invalid resets,
latch retention across restart and a new successful delivery after explicit reset.

## Measured Verification

October 16-17, 2026, WSL2 / ROS 2 Jazzy / Gazebo Harmonic, one loaded robot moving
from Vision toward Processing A at approximately 0.45 m/s:

| Independent trial | Zero-command observation | Stable odometry stop | Manager restart needed for stop |
|---|---:|---:|---|
| Manager killed, run 1 | 0.536 s | 1.067 s | No |
| Manager killed, run 2 | 0.478 s | 1.005 s | No |
| Manager killed, run 3 | 0.479 s | 1.058 s | No |
| Manager-loss median | 0.479 s | 1.058 s | No |
| Manager-loss worst observed | 0.536 s | 1.067 s | No |
| Backend suspended | 0.695 s | 1.217 s | No |
| Ungated baseline rerun (one trial) | 5.760 s | 6.160 s | Yes |

All three manager-loss runs met the two-second engineering target. Each retained
the payload, prevented false delivery, rejected invalid resets, stayed latched
across manager restart, and delivered a new product after explicit reconciliation
and reset. The saved SQLite events for all three confirm the specific latch reason
`Manager heartbeat timeout`. A preliminary run measured 0.476 s inhibition and 0.976 s stop; it is
not included in the three-run aggregate. The backend-suspension run also verified
explicit reset and a subsequent delivery.

The normal loaded destination-fault trial passed: A was invalidated, cancellation
took 0.825 s, the scheduler issued B as replacement, and B delivery occurred
11.496 s after fault injection. The payload stayed attached and the product then
passed camera/processing/quality and reached Accepted. This was a planned hold,
not an operator-reset path. Evidence: `logs/amr_smoke/replan_result.json`.

One subsequent charging verification attempt stopped before production because
the fresh verifier's DDS graph had not yet satisfied the strict sole-publisher
assertion. The checker now allows up to five seconds for discovery while still
requiring exactly the intended publisher; unexpected publishers still fail.
The rerun passed: SOC increased gradually to the configured 80% target, deferred
work resumed, real Gazebo-camera inspection passed and the product reached
Accepted. Final SOC was 76.81% after transport, with one charge cycle and 30
modeled charging seconds. The verifier observed 356 standard ROS BatteryState
samples. Evidence: `logs/amr_smoke/energy_result.json`.

An ungated comparison attempt timed out on the verifier's 0.4-second HTTP read
before fault injection, so it yielded no crash measurement. Read timeouts now
retry within the existing overall verifier deadline; production watchdogs and
physical stop thresholds were not relaxed.
The successful rerun restored the old ungated smoother path with initial speed
0.45 m/s on the same loaded Vision-to-A leg. It retained the payload at Vision,
reported failure rather than delivery, and held stationary for three seconds
after restart-triggered cancellation. Evidence: `logs/amr_smoke/manager-restart.json`.
Its 6.160-second stop is a new single observation, not a replacement for or a
guarantee derived from the historical 4.29-5.87-second samples. Only the three
independent-manager-loss trials are used in the reported median/worst aggregate.

An initial named-goal diagnostic exposed a startup race: the verifier had sensor
data, but the gate's authorization event showed `odometry_age_ms: null`. The gate
latched `Odometry timeout` and the robot never moved. Readiness now waits for the
gate's own first/fresh odometry report in both diagnostic and production paths.
The 0.5-second watchdog and explicit-reset requirement remain unchanged.
The corrected diagnostic then reached Vision, Processing A and Quality in 8.9,
10.2 and 10.1 seconds, respectively, with final position errors of 0.11, 0.12
and 0.11 m under the existing Nav2 goal checker. Straight and turning manual
drive through the gate also passed. Nav2 planned all 72 directed station pairs;
this is planning coverage, not a claim of driving all 72 routes.
Live `ros2 node list` and `ros2 topic info /cmd_vel -v` confirmed the separate
node and exactly one final publisher, `reconfactory_amr_safety`.

A final production-manager crash trial after the readiness fix also passed:
0.485 s to command inhibition and 1.015 s to stable stop, with explicit
`Manager heartbeat timeout` evidence. Restart kept the latch, invalid resets were
rejected, and explicit reconciliation/reset permitted a new delivery. This
additional regression trial is recorded separately at
`logs/amr_smoke/safety_manager-crash_1792259621189857590.json`, outside the original
three-run aggregate.

The gate-death run **did not stop automatically**: after 1.5 seconds without the
gate, measured speed remained 0.45 m/s. There was no new final zero command and no
confirmed physical stop before cleanup. The verifier's successful exit means the
failure behavior was observed and cleanup worked, not that gate death is safe.

Raw repeated-trial evidence: `logs/safety_campaign_1792184421602814132/results.json`.
That campaign was interrupted during gate-test startup; it is not an eight-trial
success report. The completed gate-death rerun is
`logs/amr_smoke/safety_gate-crash_1792258415245475419.json`.
Logs are generated local artifacts, not required repository assets. Use the
campaign command above to produce a fresh report on your own machine.

Regression checks: **316 Python tests pass on Windows and WSL**, preserving all
276 baseline tests. New policy/API tests cover freshness, replay, task/mission
mismatch, NaN/infinity, stopped windows, explicit reset, stale observation,
serialization and SQLite transition deduplication. Ruff lint and formatting pass.
The JavaScript harness covers nine movement, one health-card, two replanning,
two energy and three safety-banner scenarios. Node.js is unavailable in this
environment; the same harness is executed using the tool's V8 runtime, while CI
retains the standard `node tests/frontend_movement.test.js` command.

Both ROS packages (`reconfactory_amr`, `reconfactory_ros`) passed `colcon build`.
Integration dependency checks, shell syntax and `git diff --check` passed.
All test-owned backend, Gazebo, Nav2 and gate processes were stopped afterward.

Publication recheck on October 18: all 316 tests passed again on Windows and
ROS-sourced WSL; Ruff lint/format, the 17 browser scenarios in V8, dependency
discovery, shell syntax and whitespace checks also passed. The live measurements
above remain the October 16-17 runs, not a new campaign.

These are individual simulation observations, not guaranteed timing bounds. No
physical robot, hardware interlock, certification or long-duration endurance test
is claimed.

## Gate-Process Failure And Limits

The installed Gazebo Harmonic DiffDrive implementation retains its last target
velocity; its [Gazebo Sim 8 source](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/diff_drive/DiffDrive.cc)
does not implement a command-age timeout. No invented timeout plugin parameter is
added. A killed gate cannot send zero, and there is **no independently enforced
actuator stop bound** in this implementation. The gate-crash test observes this
condition, then uses a test-only zero publisher for cleanup. That cleanup publisher
is not a production watchdog or evidence of fail-safe behavior.

Other limits:

- ROS graph is trusted. Another publisher can bypass final velocity ownership;
  integration checks detect duplicates, but DDS access control is not configured.
- Twist has no mission stamp. Local receipt freshness, depth-one queues and
  transition clearing limit replay but do not authenticate delayed network data.
- The gate latch is in memory, not persistent across a gate/whole-stack restart.
  Restart requires operator inspection, not an assumption that an old fault cleared.
- Reset observes the manager's NavigateToPose ownership. Externally started Nav2
  behavior actions are outside the supported single-manager mission interface.
- Paused simulation can make odometry stale and latch; this is intentional.
- ROS/bridge/Gazebo death, CPU starvation and physical braking need independent
  actuator/hardware protection for a real deployment. Simulation tests are not a
  real-time or safety-certification argument.

## Implementation Map

Added:

- `reconfactory/amr_safety.py`
- `ros2_ws/src/reconfactory_amr/reconfactory_amr/safety_supervisor.py`
- `ros2_ws/src/reconfactory_amr/config/safety.yaml`
- `tests/test_amr_safety.py`
- `scripts/check_amr_safety.py`
- `scripts/run_safety_campaign.py`
- `docs/AMR_SAFETY_SUPERVISOR.md`

Modified:

- `reconfactory/amr_transport.py`, `reconfactory/supervisor.py`: observation,
  event deduplication, stable persistence IDs; production decisions unchanged.
- `app/main.py`, `frontend/app.js`, `frontend/index.html`: existing API and banner.
- `ros2_ws/src/reconfactory_amr/reconfactory_amr/manager.py`: lease and reset eligibility.
- `ros2_ws/src/reconfactory_amr/launch/amr_navigation.launch.py`: independent process,
  smoother routing and isolated historical-path comparison.
- `ros2_ws/src/reconfactory_amr/package.xml`, `ros2_ws/src/reconfactory_amr/setup.py`:
  service dependency and executable entry point.
- `scripts/run_amr.sh`, `scripts/run_amr_smoke.py`, `scripts/check_amr_pipeline.py`,
  `scripts/check_amr_resilience.py`: launch and bounded verification.
- `tests/test_api_responsiveness.py`, `tests/frontend_movement.test.js`:
  API and browser regressions.
- `README.md`, `docs/architecture.md`, `docs/api.md`, `docs/AMR_NAVIGATION.md`,
  `docs/FAULT_AWARE_REPLANNING.md`, `docs/ENERGY_AWARE_AMR.md`,
  `docs/DEMO_SCENARIOS.md`, `docs/ROS2_INTEGRATION.md`, `docs/GAZEBO_FALLBACK.md`:
  current flow, commands, recovery and limitations.

Factory scheduling, payload pose authority, camera classification and the battery
model remain unchanged. No schema migration or new browser/Windows ROS dependency
is introduced.
