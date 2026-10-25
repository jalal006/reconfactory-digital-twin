# Copied-workspace recovery, 24–25 October 2026

The recovered checkout is based on `fbb6741` (independent AMR motion supervision).
At the start of recovery, the Gazebo actuator watchdog and its integration were
existing, uncommitted work; they are included in this update.
No tracked files were reported missing by `git ls-files --deleted`.
Existing source changes and historical experiment logs were preserved.

## Environment recovery

The initially installed WSL distribution named `Ubuntu` reports Ubuntu 26.04.
Installed `Ubuntu-24.04` alongside it for this project's ROS 2 Jazzy / Gazebo
Harmonic stack. Select it explicitly with `wsl -d Ubuntu-24.04`.

The copied Linux virtual environment's Python entry points did not run Python.
Preserved that environment and the generated ROS build/install trees under
`logs/recovery-copy-20261024/` before recreating them. These generated artifacts
should be rebuilt after copying a project between machines; source is preserved.

## Checks completed during this recovery

| Check | Result |
|---|---|
| Windows Python 3.13.14, `python -m pytest -q` | 354 passed, 136.52 seconds |
| Full Python suite after snapshot batching, 25 October | 356 passed, 30.95 seconds; Ruff lint/format passed |
| Ubuntu Python 3.12 with ROS Jazzy sourced, final checks | 356 passed, 31.24 seconds; Ruff lint/format, all 20 browser scenarios and `git diff --check` passed |
| `python -m ruff check .` | Passed |
| `python -m ruff format --check .` | Passed, 98 files already formatted |
| Ubuntu standalone C++17 policy suite, warnings treated as errors | 24 passed |
| `node tests/frontend_movement.test.js` | 20 scenarios passed |
| Clean `colcon build --symlink-install` | All 3 packages built, 35.9 seconds |
| `colcon test --packages-select reconfactory_gazebo_watchdog` | Passed; test-result reports 25 entries, 0 failures |
| Gazebo version and plugin environment hook | Sim 8.15.0; watchdog install/lib is on the plugin search path |

The plugin was built against the installed Sim 8 interfaces. The live trials
below also verified automatic loading, command-topic ownership, stopping and
explicit recovery through the normal launcher.

## Historical evidence recovered

The historical campaign `logs/safety_campaign_1792719065527427144/results.json`
contains two passing gate-crash trials with stable stops at approximately 0.795
and 0.797 seconds. The later campaign
`logs/safety_campaign_1792789730446408784/results.json` contains one passing
trial and two failures: both failures stopped but failed the new-delivery check
after reset with stale backend authorization. Those trials remain failures.

These are recovered historical records, not new measurements of the restored
environment. They do not establish completion of the requested milestone.

## First live recovery trial and backend fix

The first restored-environment gate-crash trial stopped at 0.827383 s, with
0.1259999 m odometry travel from an initial speed of 0.45 m/s. The first observed
zero actuator command arrived at 0.389769 s. No cleanup publisher was used;
the latch, retained payload, denied invalid reset and explicit reset checks
passed. The subsequent mission failed with stale backend authorization, so
the overall trial **failed**. Its logs are preserved in
`logs/recovery-gate-before-batching/`.

Station snapshot persistence was measured on the Windows-mounted workspace:

| Implementation | Five observation-write times, seconds |
|---|---|
| Separate station commits | 0.2408, 0.2626, 0.2870, 0.2914, 0.2505 |
| One atomic station batch | 0.0410, 0.0443, 0.0432, 0.0418, 0.0426 |

`DataLogger.log_machine_snapshots` now commits all stations in one transaction.
The supervisor uses it for each station observation. Each machine row, history
row, sensor sample and maintenance transition remains recorded. Failure rolls
back the batch and restores the maintenance deduplication cache. This reduces
synchronous disk work on the API event loop without relaxing authorization,
command, heartbeat or odometry deadlines. Database and maintenance regressions:
33 passed, including new commit-count/data-preservation and rollback tests.

The first post-fix gate trial passed the complete sequence, including the new
delivery: 0.319845 s to actuator zero, 0.761457 s to confirmed stop, and 0.121500 m
travel. It is archived in
`logs/safety_campaign_1792875821410321921/results.json`. The next trial was
interrupted during startup when the session ended and is not counted as a pass.
Verification resumed on 25 October with the remaining scenarios.

## Three passing gate-crash trials after the fix

All started at approximately 0.45 m/s on loaded delivery, verified both command
topics' publisher ownership, and passed stable odometry stop, payload retention,
latched inhibition after ROS gate restart, invalid-reset rejection, explicit
recovery and a newly authorized delivery. No cleanup velocity publisher or manager
restart was required to initiate stopping.

| Trial | Zero command, s | Stable stop, s | Travel, m | Local command age at timeout, ms |
|---|---:|---:|---:|---:|
| 1, before interruption | 0.319845 | 0.761457 | 0.121500 | 323.407 |
| 2, resumed campaign | 0.365218 | 0.749506 | 0.117000 | 306.810 |
| 3, resumed campaign | 0.313831 | 0.759590 | 0.135000 | 305.505 |
| Median | 0.319845 | 0.759590 | 0.121500 | 306.810 |
| Worst observed | 0.365218 | 0.761457 | 0.135000 | 323.407 |

Resumed results and per-trial logs:
`logs/safety_campaign_1792893699080001989/`. The first trial is in the earlier
campaign cited above. Times begin at kill-signal dispatch; the stable-stop measure
includes the verifier's stationary confirmation window. Observed command-zero
times include bridge and verifier sampling latency, not just plugin execution.
They do not independently isolate Gazebo callback latency. These simulation
observations meet the approximate 1.5-second target; they are not certified bounds.

## Completed live regression campaign

All seven resumed scenarios exited successfully; together with the first
post-fix gate trial, this provides three complete passing gate-crash experiments.

| Scenario | Result |
|---|---|
| Manager crash | Passed; stable stop 1.121363 s; new delivery after controlled reset |
| Backend outage | Passed; stable stop 1.080598 s; new delivery after controlled reset |
| Destination fault replanning | Passed; loaded A mission cancelled, payload retained, B replacement delivered, Accepted output |
| Autonomous charging | Passed; low-SOC deferral, charger arrival, 30 simulated seconds charging, resumed production to Accepted output |
| Normal production | Passed; Nav2 delivery, real Gazebo camera inspection, processing, quality and Accepted output |
| Sensor/navigation checks | Live LiDAR, odometry, TF, sole ROS command publisher and all 72 directed route plans passed in each trial |

The charging trial consumed one charge cycle, recorded 351 ROS BatteryState
samples and finished production at approximately 76.8% SOC. Planned zero-command
holds and stationary charging did not cause an unexpected actuator latch in
these runs. The failed pre-batching trial and interrupted attempt remain recorded;
neither is counted as a pass.

## Reproduction on the restored machine

In PowerShell, select the installed version explicitly:

```powershell
wsl -d Ubuntu-24.04
```

Then in Ubuntu:

```bash
cd /mnt/c/Users/ahadd/Desktop/production_line
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build --symlink-install
colcon test --packages-select reconfactory_gazebo_watchdog
colcon test-result --verbose
source install/setup.bash
cd ..
python3 scripts/run_safety_campaign.py --manager-trials 1 --gate-trials 3
.venv-wsl/bin/python -m pytest -q
.venv-wsl/bin/python -m ruff check .
.venv-wsl/bin/python -m ruff format --check .
node tests/frontend_movement.test.js
```

For ordinary operation: `TRANSPORT_MODE=amr bash run_ubuntu.sh`.
Stop ordinary demo instances before running the isolated campaign.

## Scope and limitations

The existing plugin, bridge routing, startup-inhibited / armed / latched policy,
explicit operator reset, ROS supervisor, API/dashboard observations and transition
events were retained and verified. The snapshot-batching implementation is in
`reconfactory/logger.py` and `reconfactory/supervisor.py`, with database tests in
`tests/test_data_logger.py`. README and watchdog documentation link this record.

No production state is advanced by a watchdog stop. Existing task reconciliation
and Nav2 success still determine delivery. Gate-crash recovery tests explicitly
checked retained payload and no false delivery before resetting the demo run.

The old architecture's 0.45 m/s motion after 1.5 seconds remains historical
evidence, not a newly measured paired baseline. No hardware safety, real-time
deadline, arbitrary-process isolation or protection against a frozen Gazebo
process is claimed. Whole-Gazebo restart loses the in-memory latch; external
publishers can bypass intended topic ownership in this trusted simulation graph.
See the watchdog design document for the complete recovery contract and limits.

## Follow-up: a second fault during the manager-crash test

The user's campaign `logs/safety_campaign_1792939461997138503/results.json`
passed seven of eight trials, including all three gate crashes. The manager-crash
trial stopped correctly in 1.089457 seconds, retained its payload and rejected
automatic recovery. It failed the final delivery check because the actuator also
latched on a 304.388 ms command gap. The harness reset only ROS safety for this
scenario, leaving the actuator correctly inhibited. This campaign remains a
failed campaign; the second latch was a real observed command gap, not a fabricated
measurement or an ignored timeout.

The harness now chooses the explicit recovery steps from both observed states,
regardless of the failure-injection scenario. After operator reconciliation it
resets ROS safety first if latched, resets the actuator if latched, and requires
fresh stopped observations plus actuator readiness before authorizing the next
test mission. A service success alone no longer counts as completed recovery.
The result records `recovery_layers_reset`. Production reset services, timeout
values and fault latches are unchanged; this is limited to the test's existing
explicit recovery phase, with no reset attempts during resumed production.

Eleven new regression cases cover both-latched recovery ordering, healthy-actuator
preservation, stale observations, non-disarmed gates, moving and invalid odometry.
The updated full suites passed 367 tests on Windows (20.70 s) and Ubuntu
(24.98 s); Ruff lint and formatting passed.

Post-fix live retests passed:

| Scenario | Stable stop | Layers explicitly reset | New delivery |
|---|---:|---|---|
| Manager crash | 1.057495 s | ROS safety; actuator stayed healthy | Passed |
| Gate crash | 0.766527 s | Gazebo actuator | Passed |

Measurements are saved as
`logs/amr_smoke/safety_manager-crash_1792941186623644225.json` and
`logs/amr_smoke/safety_gate-crash_1792941348271841662.json`.
Both-latched ordering is covered deterministically by the new unit regression;
the additional actuator latch did not recur in the manager-crash retest. The
underlying intermittent command gap has not been independently attributed to a
specific scheduling or transport cause. No timeout was relaxed to suppress it.

## Dashboard detection and publication checks, 25 October

Both ROS packages were installed even when the dashboard displayed `missing`.
The camera probe could select the dashboard virtualenv's NumPy 2 instead of
Ubuntu's ROS-compatible system Python. Probes now use `/usr/bin/python3`;
the camera check performs an image conversion, and Nav2 checks its three package
entries in a single process. The subprocess budget is 15 seconds, and unsuccessful
commands cannot count as successful detections. A timeout still appears as
`missing`; this UI label alone is not evidence of an absent apt package.

The corrected detector reported every integration ready with the launcher ROS
workspace and virtualenv sourced. Six API responsiveness tests passed. Before
publication, the full Ubuntu suite passed **367 tests in 30.61 seconds**, Ruff
lint and format checks passed (120 files), and all 20 browser scenarios passed.
The earlier Windows and live simulation results above remain separate runs;
no new full live campaign is claimed for this documentation update.

The user's additional manager-crash report
`safety_manager-crash_1792941963773957449.json` passed with command inhibition at
0.494168 seconds, stable stop at 0.963714 seconds and 0.171 m travel. Payload was
retained, restart did not clear the latch, explicit ROS-layer reset succeeded,
and the new authorized mission delivered. It does not overwrite the failed
campaign recorded above. Raw runtime logs remain local and ignored by Git.
