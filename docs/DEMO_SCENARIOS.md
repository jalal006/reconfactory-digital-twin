# Demo Scenarios

## Fault During AMR Delivery

Run AMR mode and inject Processing A Overheat while a loaded red block is travelling
from Vision to A. Show cancellation, the payload remaining on the robot, the linked
replacement to B, and processing only after delivery. Fault both drills to show safe
waiting; recover B to resume. See [Fault-Aware Replanning](FAULT_AWARE_REPLANNING.md)
for a 45-60 second recording outline and the isolated `--fault-replan` runtime check.

## AMR Portfolio Demo (45-60 Seconds)

Run the [AMR setup](AMR_NAVIGATION.md) first and wait for `AMR ready`.
Record the browser, Gazebo and optional RViz side by side. Show one red product
waiting at Input, then the robot picking it up and navigating to Vision. Show
the task's `navigating` and `delivered` events alongside the camera debug image.
Finish with the robot delivering to Processing A and the machine starting only
after delivery. Use clearly labeled cuts/time compression to show Quality and
Accepted: a full conservative-speed production cycle takes longer than a minute.
Do not describe logical payload placement as physical grasping.

## Demo 1: Normal Production

1. Click `Start`.
2. Add red, blue, and green products.
3. Watch completed and accepted products increase.

## Demo 2: Station Failure And Rerouting

1. Add a red block.
2. Let it reach Processing A.
3. Click `Station A Overheat`.
4. Watch the product reroute to Processing B if drilling is still possible.

## Demo 3: Conveyor Jam

1. Start production.
2. Click `Conveyor Jam`.
3. Confirm the line stops safely.
4. Recover the conveyor.

## Demo 4: Defective Product

1. Choose a defect such as `wrong_colour`.
2. Add the product.
3. Confirm it goes to reject output after vision inspection.

## Demo 5: No Available Route

1. Fail Processing A.
2. Add a green component.
3. Confirm it pauses safely because assembly has no backup station.

## Demo 6: Predictive Maintenance

From the repository root in an activated Ubuntu project environment:

```bash
python scripts/train_health_model.py
MAINTENANCE_MODE=ml HEALTH_AWARE_SCHEDULING=1 python scripts/run_factory.py
```

1. Open the dashboard, press Start and wait for the 12-sample warmup.
2. Confirm machine cards show `ml_isolation_forest`, then add red blocks.
3. In another activated terminal, run
   `python scripts/demo_machine_health.py --machine station_a --scenario bearing`.
4. Show A's increasing anomaly score and a `predictive_reroute` event choosing B
   for new compatible work before a hard fault. Existing work stays assigned.
5. Reset afterward: late degradation samples can trigger a real simulated fault.

For the reproducible comparison, run
`python scripts/run_experiment.py --maintenance --seed 42 --ticks 180`.
The measured trial completes 23 products in both modes, with 18 predictive
diversions and lower anomaly at assignment, but slightly longer cycle times.
Do not describe this as increased throughput or prevention of the imposed fault.

For a 45-60 second recording, show the score/source, changed assignment and
comparison table. See [Predictive Maintenance](PREDICTIVE_MAINTENANCE.md) and
[measured results](MAINTENANCE_VERIFICATION.md).

## Battery-Aware Autonomy

Run `AMR_INITIAL_SOC=0.21 TRANSPORT_MODE=amr bash run_ubuntu.sh`, add a red block,
then Start. Show its unchanged input location, the deferred intent and the empty
robot navigating to the green charger pad. Show SOC rising gradually to 80%, then
the fresh production task and pickup. For a 45-60 second clip, show the charger
arrival, a short charging segment, and resumed delivery with the event log; disclose
any time cuts. End on the comparison report rather than claiming faster transport.
Full procedure and limitations: [Energy-Aware AMR](ENERGY_AWARE_AMR.md).

## Independent Motion Supervision

Stop the normal demo and run `python3 scripts/run_amr_smoke.py --safety manager-crash`
from a sourced Jazzy/workspace terminal. This starts an isolated stack and prints
its dashboard URL. The verifier kills only its own AMR manager during loaded
navigation, observes stopping before restart, tests invalid resets, reconciles the
aborted run and checks a new delivery after explicit reset.

For a 45-60 second recording, omit startup and disclose time cuts: show authorized
loaded travel, the latched dashboard state and physical stop, a rejected reset,
then explicit recovery and a fresh delivery. Finish with measured inhibition and
stable-stop timings. State that killing the gate itself does not have an enforced
actuator timeout; this is simulation command supervision, not certified safety.
See [architecture, reproducible trials and results](AMR_SAFETY_SUPERVISOR.md).
## Gazebo Gate-Death Demonstration

For the independent actuator protection demo, stop the regular stack and run
`python3 scripts/run_amr_smoke.py --safety gate-crash` in a sourced Jazzy terminal.
The isolated harness loads a red product, kills only the ROS safety process during
delivery and measures Gazebo actuator zero plus stopped odometry. No cleanup
publisher initiates stopping. It also checks retained payload, restart inhibition,
invalid reset, explicit recovery and a new delivered mission. See
[configuration, measurements and remaining limits](ACTUATOR_DEADMAN_WATCHDOG.md).
