# Energy-Aware AMR

The supervisor owns battery state and admission decisions. The existing AMR
manager owns one Nav2 action sequence. There is no second charging navigator,
new scheduler, or independent battery simulation in ROS.

## Data Flow

```text
Gazebo odometry -> manager cumulative motion counters -> backend Battery
backend EnergyPolicy -> production task OR charging task -> existing Nav2 runner
Nav2 success + localized dock pose + stopped odometry -> gradual charging
charge target -> scheduler revalidation -> fresh production authorization
backend energy snapshot -> dashboard + ROS sensor_msgs/BatteryState
```

Motion counters include a manager session ID and monotonically increasing sequence,
elapsed simulation seconds, distance and absolute rotation. Replays do not consume
energy again. A restarted manager establishes a fresh baseline; old sessions are
ignored. Missing telemetry does not imply a successful delivery or recharge.

## Model And Configuration

This is a **deterministic simulation model, not a validated physical battery model**.
All coefficients are in [config/energy.yaml](../config/energy.yaml).

```text
consumption_Wh = idle_W * dt_s / 3600
               + payload_factor * (linear_Wh_per_m * abs(v_m_s)
                                  + angular_Wh_per_rad * abs(w_rad_s)) * dt_s
SOC = remaining_Wh / capacity_Wh
charge_Wh = charging_W * dt_s / 3600
```

Consumption is clamped at zero remaining energy. Charging also pays idle load,
increases gradually, and stops at the configured target, not at an arbitrary timer.

| Parameter | Default |
|---|---|
| Capacity / initial SOC | 100 Wh / 0.90 |
| Idle load | 18 W |
| Linear / angular motion | 0.2 Wh/m / 0.03 Wh/rad |
| Loaded motion multiplier | 1.25 |
| Planning reserve / critical reserve | 0.20 / 0.05 |
| Charge target / charging power | 0.80 / 7200 W |
| Estimated speed / turn allowance | 0.35 m/s / pi rad per leg |
| Estimate safety factor | 1.4 |
| Charger arrival tolerance | 0.18 m |

The charging rate is deliberately accelerated for a short demo, not realistic
charger sizing. `AMR_INITIAL_SOC=0.21` overrides initial SOC without editing YAML.

## Authorization And Priorities

Before dispatch, estimate empty travel from current pose to pickup and loaded
travel to destination using Euclidean distance, estimated idle time, turn allowance
and safety factor. Preserve the planning reserve and enough estimated empty travel
from the destination to the charger above critical reserve. This distinguishes a
short affordable mission from a longer unaffordable one at the same SOC.

An insufficient budget defers an intent, not an executing product task. Product
location stays unchanged. The charging task uses `mission_type=charge`, a non-product
ID `AMR`, `payload_loaded=false`, and destination `charging_dock`. Only a successful
Nav2 arrival with a matching localized pose enables charging. Moving away, moving
instead of stopping, stopping production, or losing telemetry prevents recharge.
On reaching target, release the same mission slot and rerun the existing scheduler;
do not blindly replay a stale station choice. An impossible target-budget mission
or unreachable charger enters an explicit blocked/critical state.

Priority is stop/emergency and hard-fault cancellation, critical-energy hold,
fault-replacement feasibility, then routine charging and new production dispatch.
Loaded work is not abandoned for a routine planning-reserve threshold. A safe loaded
mission continues; insufficient energy for its remaining leg plus critical reserve
requests cancellation and retains the payload. Fault replanning still waits for
the old Nav2 result and stopped odometry before authorizing a replacement. Loaded
replacement feasibility uses the current pose and critical reserve, without a new
pickup. Unsafe replacements remain held rather than creating a competing charger goal.

Critical/failed charging missions require operator inspection and reset; there is
no automatic teleport, battery refill in place, or retry loop. Reset starts a new
simulation and reinitializes the configured battery; it is not physical recovery.

## Charger And Observability

The generated AMR world has a cabinet and ground pad near `(-1.2, -1.3)` in `map`.
The goal lives in `ros2_ws/src/reconfactory_amr/config/stations.yaml`, and the cabinet
position in `factory_layout.yaml`. Navigation and localization maps include the
charger geometry; the original conveyor world is unchanged.

`GET /api/status` and `GET /api/transport` expose `energy`: SOC, remaining/consumed/
charged Wh, state, reserve, estimated mission energy, deferred intent, charge count
and charging duration. The dashboard shows these beside the transport state.
Transition events use existing SQLite event JSON: deferral, requested charge,
started/completed/failed charge, critical hold and transport terminal outcomes.
Transport events contain estimated/actual Wh, task/product/robot IDs and times.
Motion heartbeats do not create per-frame database events.

`/reconfactory/amr/battery_state` publishes standard `sensor_msgs/msg/BatteryState`.
`percentage` is 0..1, `present=true`, status reflects charging/discharging. Voltage,
current, temperature and Ah fields are unknown (`NaN`); Wh is not mislabeled as Ah.

## Run And Verify

From the repository root in Ubuntu/WSL:

```bash
AMR_INITIAL_SOC=0.21 TRANSPORT_MODE=amr bash run_ubuntu.sh
```

Open the printed dashboard URL, add a red block and start. The product stays at
input while the empty robot travels to the charger. SOC rises over roughly 30
simulation seconds, then the robot picks up the product for normal camera inspection
and production. The station indicators remain governed by actual delivery.

For a bounded isolated headless test that stops its own stack afterward:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
python3 scripts/run_amr_smoke.py --energy
ros2 topic echo /reconfactory/amr/battery_state --once
```

Run the topic command in another terminal while a normal stack is running; the
isolated test uses domain 73 and shuts down before returning. It verifies actual
BatteryState delivery, sensors, TF, Nav2 plans including charger, gradual charging,
deferred input and resumed real-camera production. Results: `logs/amr_smoke/energy_result.json`.

Pure Python verification and experiment, without sourcing ROS:

```bash
.venv-wsl/bin/python -m pytest
.venv-wsl/bin/python -m ruff check .
.venv-wsl/bin/python -m ruff format --check .
.venv-wsl/bin/python scripts/compare_energy_policies.py
```

PowerShell browser demo: `$env:AMR_INITIAL_SOC="0.21"; .\run_powershell.ps1`.
Browser-only mode gates logical input/processing/quality transfers with the same
policy and simulates a timed charger trip. It preserves existing conveyor visuals;
there is no physical robot. Terminal conveyor output is not a separate logical
AMR leg in this fallback. Full AMR mode accounts for the output delivery as usual.

## Reproducible Comparison

`compare_energy_policies.py` runs the same ten-red-block workload, station poses,
0.35 m/s logical travel, 100 Wh capacity and initial SOC 0.21 in both arms.
The baseline skips admission gating but retains the same consumption and critical
hold. The energy-aware arm uses the actual supervisor charging policy.

Report: `data/generated_reports/energy_comparison.json`. A baseline that cannot
finish has `completion_time_s=null`, not a fabricated completion time. Inspect
completed count, unfinished count, critical stops, minimum SOC, charged/consumed
Wh, charging duration and estimate-minus-actual error together. More travel and
energy in the aware arm may simply mean it completed more work.

This experiment uses straight-line logical movement with no angular motion or Nav2
obstacles. Estimates are conservative geometric approximations, not costmap path
integrals. It demonstrates policy behavior, not improved physical battery life or
faster navigation. Live odometry includes turns, detours and idle time; energy
accounting is approximate at phase boundaries between 4 Hz manager heartbeats.
State is not restored across a full backend restart; inspect/reset the physical
simulation after lost mission ownership. No hardware battery, charger contact,
thermal behavior, voltage curve, or physical battery lifespan is modeled.

## Measured Verification (2026-10-05)

The deterministic comparison produced:

| Metric | Ungated baseline | Energy-aware |
|---|---:|---:|
| Products completed / created | 2 / 10 | 10 / 10 |
| Critical energy holds | 1 | 0 |
| Minimum SOC | 5.60% | 20.70% |
| Charging cycles / seconds | 0 / 0 | 1 / 30 |
| Energy consumed | 15.40 Wh | 58.50 Wh |
| Total workload completion | Unfinished | 790 logical seconds |

The baseline was observed for 202 logical seconds before its critical hold. These
are not equal-output performance numbers: the aware policy completed more work
and used more energy. Mean estimate minus actual per delivered aware mission was
0.855 Wh in this straight-line experiment.

The first live isolated Gazebo run completed charging plus a real-camera inspected
red block in about 97.4 wall seconds. SOC reached 80% after 30 simulation charging
seconds and decreased to 76.83% by final delivery. The separate loaded-fault run
cancelled delivery to A, retained its payload, replanned to B and completed in 61.4
wall seconds; measured cancellation was 1.34 s and replacement authorization 0.54 s.
These are individual local runs, not timing guarantees. Both verified all 72
directed station-pair plans, live LiDAR/odometry/TF and the BatteryState topic.

A second charging run checked 350 actual ROS BatteryState messages, including
charging status and decreasing SOC after departure. It completed in 99.7 wall
seconds; final ROS SOC was 0.7682985 versus backend 0.7682840. The earlier attempt
at this stronger verifier exposed an rclpy callback-signature error in the test
script; the callback was fixed before this successful rerun. The live stack had
one battery publisher and one AMR manager. Test-owned services were stopped.

Regression verification on October 6: 276 Python tests passed on Windows and WSL,
preserving the previous 241 tests, adding 34 energy tests and a ROS-plugin isolation
regression. The WSL suite also passed with ROS and the workspace sourced: root
pytest configuration excludes `launch_testing` and `launch_ros`, which otherwise
pull ROS launch dependencies into the ROS-independent unit suite. Live integration
scripts are unaffected. Ruff lint and formatting passed.
The JavaScript harness passed 9 movement, 1 health-card, 2 replanning-banner and 2
energy-banner scenarios. ROS `colcon build` passed for both packages. Docker runtime,
hardware batteries and physical charging were not tested. Dashboard behavior was
tested through the JavaScript harness, not a new visual screenshot assessment.

## Implementation Files

Added: `config/energy.yaml`, `reconfactory/energy.py`,
`reconfactory/energy_policy.py`, `tests/test_energy.py`,
`scripts/compare_energy_policies.py`, and this document.
Release verification also adds `tests/test_pytest_environment.py`.

Modified core/API: `reconfactory/supervisor.py`, `reconfactory/amr_transport.py`,
`reconfactory/transport.py`, `app/main.py`.

Modified browser/tests: `frontend/app.js`, `frontend/index.html`,
`tests/frontend_movement.test.js`.
Release verification updates `pyproject.toml` and `.github/workflows/tests.yml`.

Modified under `ros2_ws/src/reconfactory_amr/`: `reconfactory_amr/manager.py`,
`reconfactory_amr/navigation.py`, `config/stations.yaml`, `config/factory_layout.yaml`,
`maps/reconfactory_map.pgm`, `maps/reconfactory_lidar_map.pgm`.

Modified scripts: `scripts/generate_amr_map.py`, `scripts/check_amr_pipeline.py`,
`scripts/run_amr_smoke.py`.

Modified documentation: `README.md`, `docs/architecture.md`,
`docs/AMR_NAVIGATION.md`, `docs/FAULT_AWARE_REPLANNING.md`, `docs/DEMO_SCENARIOS.md`,
`docs/ROS2_INTEGRATION.md`, `docs/GAZEBO_FALLBACK.md`.
The transport/energy HTTP contract is documented in `docs/api.md`.
