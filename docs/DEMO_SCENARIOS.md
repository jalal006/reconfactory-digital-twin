# Demo Scenarios

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
