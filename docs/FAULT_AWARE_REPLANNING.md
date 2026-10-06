# Fault-Aware In-Flight Replanning

Hard destination faults invalidate an authorized AMR mission. Predictive-health
score changes do **not** cancel missions. The existing scheduler still applies
capabilities, station availability, occupancy and optional health penalties when
choosing a replacement.

## Ownership And Handshake

```text
Destination fault / hard unavailability
  -> FactorySupervisor / FactoryTransport: cancel_requested, cancelling
  -> AMR manager: cancel existing NavigateToPose
  -> terminal action result AND fresh stopped odometry for 0.3 seconds
  -> cancelled status accepted by supervisor
  -> awaiting_replan (payload held)
  -> existing ProductionScheduler selects available compatible destination
  -> linked replacement task
  -> NavigateToPose from current AMCL pose
  -> delivered -> supervisor moves product and starts processing
```

Cancellation acceptance alone is not completion. ROS distinguishes CANCELING
from terminal CANCELED in its [action status contract](https://docs.ros.org/en/rolling/p/action_msgs/msg/GoalStatus.html).
The manager additionally requires fresh odometry (under 0.5 seconds old), linear
speed below 0.03 m/s and angular speed below 0.05 rad/s for at least 0.3 seconds.
It never publishes velocity commands itself.

Existing task statuses remain unchanged. `replan_state` adds `cancelling`,
`awaiting_replan`, and `blocked_transport`. Products remain `in_transit` during
automatic recovery; their location remains the last confirmed station.
Unconfirmed cancellation/failure pauses the product and requires operator action.

## Payload And Task Contract

Normal tasks retain pickup then delivery. A replacement preserves
`payload_loaded`; a loaded replacement starts in delivery phase and sends only
the destination goal. An interrupted pickup still performs pickup.

The existing Gazebo synchronizer remains the only product pose writer. It keeps
delivery-phase cargo on the AMR through cancellation, waiting, and replacement.
No new attachment process, robot teleport, localization reset or home goal is
introduced. Logical station handoff is unchanged.

Additional task metadata: `supersedes_task_id`, `original_destination`,
`replan_reason`, `fault_id`, `payload_loaded`, `replan_state`,
`cancel_latency_s`, `replan_latency_s`. The supervisor owns these fields; status
reports cannot override scheduling metadata. Both existing ROS JSON topics
(`/reconfactory/amr/task`, `/reconfactory/amr/status`) retain their names/types.

`GET /api/transport` and WebSocket snapshots expose the active task. The browser
transport banner shows cancellation/waiting and original/replacement destinations.
SQLite event JSON records `transport_replan_requested`, `transport_goal_cancelled`,
`transport_replanned`, `transport_replan_failed`, task linkage, pose and timings.
Waiting does not produce a per-tick event flood.

## Races And Limits

- Late success cannot deliver an invalidated task. If success already reached
  the manager but not the supervisor, it is converted to cancellation after stop.
- Duplicate faults and cancellation reports do not create multiple missions.
  A bounded cache handles recent retired-task acknowledgements; older stale IDs
  are refused without moving products.
- Replacement selection occurs after cancellation, against current state. A
  replacement that faults after creation is invalidated in turn.
- No alternate: hold the loaded robot, show `awaiting_replan`, retry selection
  while running when a station recovers or becomes available. There is no fake
  delivery or instant fallback.
- Backend outage: cancel navigation, preserve ordered outgoing statuses, block
  replacement until the backend accepts cancellation. Heartbeat timeout remains
  fail-closed and may require manual recovery rather than automatic resumption.
- Rejected/failed cancellation, lost result/goal handle, or manager restart:
  fail closed. A restarted manager requests cancellation of orphan navigation
  on this **single-robot** action server, but does not claim acknowledged delivery
  or safe automatic resumption. Stop the stack, inspect payload, restart/reset.
- Pause, emergency stop and arbitrary navigation failures are not automatic
  fault replans. The previous held-payload behavior remains.
- No persistent mission restoration across backend restart. No physical gripper,
  multi-robot operation, safety certification, or ML-driven continuous switching.

## Run And Observe

From the repository root in Ubuntu/WSL:

```bash
source /opt/ros/jazzy/setup.bash
TRANSPORT_MODE=amr VISION_SOURCE=gazebo bash run_ubuntu.sh
```

Open `http://127.0.0.1:8000`, add a normal red block, Start, and inject Overheat
on Processing A **while the loaded AMR is driving from Vision toward A**.
Expect cancellation, a held payload, replacement to B, processing, then Quality.
Fault both processing stations to demonstrate safe waiting; recover B to resume.

In another sourced terminal:

```bash
source ros2_ws/install/setup.bash
ros2 topic echo /reconfactory/amr/status
# Optional separate terminal:
rviz2 -d ros2_ws/src/reconfactory_amr/rviz/amr_navigation.rviz
```

Browser-only mode remains `TRANSPORT_MODE=simulated VISION_SOURCE=synthetic`;
the PowerShell launcher needs no ROS/Nav2 installation.

## Reproduce Verification

```bash
source .venv-wsl/bin/activate
python -m pytest
python -m ruff check .
python -m ruff format --check .
python scripts/run_replanning_experiment.py
```

The paired experiment uses the same normal red product, initial A assignment and
fault timing. The static arm reproduces the previous cancel-and-hold policy; the
replanning arm enables replacement. It measures **logical ticks with scripted
action acknowledgements**, not robot physics or wall-time navigation performance.
Distance and completion delay are null when not measurable. Output:
`data/generated_reports/replanning_comparison.json`.

Observed paired result: both arms fault at tick 7 and acknowledge cancellation
one tick later. Static transport leaves one product stranded (zero completions).
Replanning authorizes a replacement one tick after cancellation, delivers four
ticks after the fault, and completes production at tick 23. No speedup over a
completed baseline or measured extra navigation distance is claimed.

With the normal stack stopped, run the isolated real-runtime check:

```bash
source /opt/ros/jazzy/setup.bash
.venv-wsl/bin/python scripts/run_amr_smoke.py --fault-replan
```

It checks sensors/TF/planning, uses real camera perception, injects the fault
after the robot leaves Vision, checks loaded replacement to B and full product
completion, and stops its own processes. Read `logs/amr_smoke/replan_result.json`
and `amr.log` for wall-time measurements and Nav2 cancellation/goal logs.
This headless check does not constitute a visual RViz path review.

## Measured Runtime (September 27, 2026)

Two real Gazebo/Nav2 runs with the stationary camera pipeline:

| Observation | Run 1 | Run 2 |
|---|---:|---:|
| Fault injected after production start | 19.72 s | 19.98 s |
| Cancellation confirmed after fault | 1.31 s | 1.51 s |
| Replacement authorization after cancellation | 0.60 s | 0.42 s |
| Delivery to B after fault | 11.32 s | 11.12 s |
| Full product completion, excluding startup | 60.74 s | 59.29 s |

The fault pose was (2.44, 0.72); replacement began near (2.67, 0.66), not at
pickup/home. The product processed at B and completed at Accepted. Sensors/TF,
the NavigateToPose server and all 56 directed station-pair plans passed.
Run 2 also asserted the Gazebo synchronizer reported the product at `amr_payload`
after fault injection. Both isolated test stacks shut down afterward.
These are two observations, not performance guarantees. Automated checks did not
include visual RViz review, real hardware or a measured extra-distance comparison.
The maintainer subsequently reported successful completion of the manual checklist,
including desktop Gazebo/RViz, fault replanning and no-alternative recovery. This
is user-reported visual confirmation, separate from the automated measurements.

Regression checks: 238 Python tests passed on Windows and WSL, including 25 new
replanning cases; Ruff lint/format passed. The JavaScript harness passed nine
movement scenarios, one health-card scenario and two transport-banner scenarios.
Both ROS packages built; the integration checker found ROS, Gazebo, Nav2,
camera bridge and backend dependencies. Pure tests cover cancellation order,
late/duplicate results, no-alternative recovery, capabilities/health selection,
failed replacement, logical Gazebo payload retention and SQLite event linkage.

## Additional Resilience Checks

Run from the repository root with the normal stack stopped:

```bash
source /opt/ros/jazzy/setup.bash
.venv-wsl/bin/python scripts/run_amr_smoke.py --resilience backend-outage
.venv-wsl/bin/python scripts/run_amr_smoke.py --resilience manager-restart
```

These scenarios use real Gazebo/Nav2 and odometry. The verifier restricts signals
to descendants of its isolated test launcher with the test ROS domain/Gazebo
partition. It resumes a suspended backend and stops its replacement manager in
cleanup. Process-selection safeguards also have ROS-free unit tests.

The three-second backend suspension passed: stopped odometry was confirmed after
2.04 seconds, the cancellation reached the supervisor after 3.11 seconds, and a
further three-second stationary hold produced no extra mission or false delivery.
This is a temporary outage test, not restoration after loss of backend memory.

Two manager-crash/restart runs also reached the intended held state. The verifier
killed only the test manager during loaded navigation, restarted it, and observed
Nav2 orphan-goal cancellation. Stop confirmation took 4.29 and 5.87 seconds;
the supervisor marked the mission failed, retained the loaded payload and did not
advance the product from its last confirmed station or issue another mission.
The second run explicitly checked manager liveness throughout the hold, Gazebo's
`amr_payload` report, and a clean shutdown (exit 0).

An earlier run logged an rclpy subscription traceback around cleanup; it did not
recur in the repeat with explicit liveness checks. This remains an observed
intermittent shutdown issue, not a claimed fix. Crash-stop latency is also a real
limitation: stopping relies on a restarted manager discovering and cancelling the
orphan goal. This is **not an independent or immediate emergency-stop watchdog**.
Persistent backend restart, prolonged outages, and an absent manager that never
restarts remain outside these runtime checks.

Results are saved in `logs/amr_smoke/backend-outage.json` and
`logs/amr_smoke/manager-restart.json`. After adding the verifier safeguards,
the full WSL regression suite passed 241 tests and Ruff lint/format passed.

RViz is installed, but an attempted offscreen render failed with OGRE/GLX
`Invalid parentWindowHandle`. The maintainer subsequently confirmed the manual
desktop checklist passed; the offscreen failure remains an automated-rendering
limitation, not evidence that normal desktop RViz is broken.
No physical robot, hardware safety, or gripper behavior has been validated.
Cancellation rejection/failure is tested with mocked action futures, not forced
against a faulty real Nav2 server.

## Change Inventory

Added:

- `analytics/replanning_experiment.py`
- `scripts/run_replanning_experiment.py`
- `tests/test_amr_replanning.py`
- `scripts/check_amr_resilience.py`
- `tests/test_resilience_verifier.py`
- `docs/FAULT_AWARE_REPLANNING.md`

Modified:

- `reconfactory/transport.py`: task metadata and loaded-task deserialization.
- `reconfactory/amr_transport.py`: invalidation, cancellation gate, scheduler reuse,
  held-payload waiting, linked replacement and events.
- `reconfactory/supervisor.py`: fault invalidation hook.
- `ros2_ws/src/reconfactory_amr/reconfactory_amr/navigation.py`: cancellation
  acknowledgement, terminal-result/stop gate, late-success and callback guards.
- `ros2_ws/src/reconfactory_amr/reconfactory_amr/manager.py`: odometry stop checks,
  cancellation metadata, restart fail-closed behavior and authorization checks.
- `frontend/app.js`, `tests/frontend_movement.test.js`: transport banner and tests.
- `scripts/run_amr_smoke.py`: isolated fault-in-flight runtime scenario.
- `README.md`, `docs/AMR_NAVIGATION.md`, `docs/architecture.md`, `docs/api.md`,
  `docs/ROS2_INTEGRATION.md`, `docs/DEMO_SCENARIOS.md`: updated diagrams, contracts,
  verification evidence and reproduction links.

No API endpoint, database schema, Nav2 tuning, Gazebo world or ML model was replaced.

## Portfolio Demo (45-60 Seconds)

Begin with an already inspected block and the loaded AMR leaving Vision. Show
the dashboard destination A beside Gazebo/RViz. Inject A Overheat. Point out
cancellation, the stopped robot holding the same payload, replacement B, and the
new path from its current pose. Finish with processing at B and the linked
transport events. For a second clip, fault both machines and recover B.

## Energy Interaction

Cancellation and stopped confirmation still precede replacement authorization.
The supervisor checks energy for the scheduler-selected replacement. Safe loaded
replacements preserve the payload and navigate directly; unsafe ones remain held
in `critical_energy`. An unloaded deferred replacement may use the same mission
slot for charging, then revalidate the station. Routine low planning reserve does
not interrupt a safe loaded mission. No charging goal runs alongside a production
or cancellation goal. See [Energy-Aware AMR](ENERGY_AWARE_AMR.md).
