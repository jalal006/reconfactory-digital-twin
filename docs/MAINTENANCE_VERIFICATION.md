# Maintenance Verification

Measured September 22, 2026 with scikit-learn 1.9.0, seed 42. Results describe
synthetic telemetry and tick-based production, not real machine prognosis.

## Model Evaluation

Training uses 24 healthy sequences (2,616 rolling windows). Calibration uses
8 separate healthy sequences (872 windows). Evaluation uses 8 further seeds:
872 healthy windows and the final 40 windows from each of 8 sequences for each
of bearing, overheating and mechanical-load degradation (960 total).
Whole sequences are separated; adjacent windows within each split are correlated.
The labels never enter Isolation Forest fitting or normalization calibration.

| Metric | Result |
|---|---:|
| Healthy false-positive rate | 0.46% |
| Degraded detection rate / recall | 88.85% |
| Precision | 99.53% |
| F1 | 0.9389 |
| Mean healthy normalized anomaly | 0.00815 |
| Mean degraded normalized anomaly | 0.85860 |
| Bearing detection | 100% |
| Overheating detection | 66.56% |
| Mechanical-load detection | 100% |

Detection means normalized anomaly >= 0.5. Late degraded windows are evaluated,
so these numbers do not establish detection latency or early-warning reliability.
An initial fixed-scale normalization detected only 48.13% of degraded windows;
the final scale instead uses healthy calibration quantiles. This is development
evaluation of simulated scenarios, not a blind external validation study.

## Paired Factory Trial

```bash
python scripts/train_health_model.py
python scripts/run_experiment.py --maintenance --seed 42 --ticks 180
```

Both arms use the same trained model, seeded telemetry, fault rules and 23 red
products (one per 6 ticks after warmup, followed by a 30-tick drain). Only the
health scheduling switch changes. A develops bearing degradation; B stays healthy.
The existing hard-fault detector runs normally and neither arm repairs the fault.

| Metric | Baseline | Health-Aware |
|---|---:|---:|
| Completed / created | 23 / 23 | 23 / 23 |
| Throughput, products/tick | 0.12778 | 0.12778 |
| Mean cycle time, ticks | 7.3913 | 7.8261 |
| Downtime, machine ticks | 20 | 20 |
| Hard faults | 1 | 1 |
| Reactive reroutes | 0 | 0 |
| Predictive diversions | 0 | 18 |
| Assignments to A / B | 14 / 9 | 4 / 19 |
| Mean anomaly at processing assignment | 0.43594 | 0.00494 |
| A utilization, busy ticks / elapsed ticks | 23.33% | 6.67% |
| B utilization, busy ticks / elapsed ticks | 20.00% | 42.22% |

The demonstrated benefit is lower-risk new assignments, not greater throughput
or fewer hard failures. The slower compatible drill increases mean cycle time
by about 5.9%. Because degradation is exogenous and identical, stopping new
assignments cannot prevent A's eventual fault. A diversion compares the selected
station against normal scheduling in that arm's current state; it is not the
same count as the difference between the two arms' aggregate A assignments.

Machine-readable metrics and model provenance are generated in
`data/generated_reports/maintenance_comparison.json`; evaluation metadata is
saved next to the local model. Generated artifacts/datasets remain gitignored.

## Runtime Verification

- **213 tests pass on both Windows and Ubuntu/WSL**, including all 183 preexisting
  tests and 30 new deterministic feature, model, scheduler, API, persistence and
  dependency-isolation cases. Ruff lint/format checks pass.
- Nine JavaScript movement scenarios and one new health-card rendering/escaping
  scenario pass using the V8 harness; Node is not installed in this environment.
- The normal isolated Ubuntu launcher rebuilt the ROS factory bridge and ran
  Gazebo camera perception, Nav2 and ML health scheduling together. LiDAR,
  odometry, TF and all 56 station-pair planning checks passed.
- A normal red product completed Input -> Vision -> A -> Quality -> Accepted in
  about 54 seconds (startup excluded), with `method=gazebo_camera` and
  `maintenance_mode=ml`, `health_scheduling_enabled=true` in the backend snapshot.
- `/reconfactory/machine_health` published real JSON predictions from the backend
  with `source=ml_isolation_forest`, 12 samples and descriptive signal statistics.
- Initial live testing exposed an eager ML import in the ROS camera process.
  Lazy imports fixed this; a regression now blocks sklearn/joblib imports while
  importing camera/core modules and running rule mode.
- Existing recovery comparison, deterministic CSV generation, integration checker
  and SQLite event export ran successfully. All isolated test services stopped.

This does not constitute a live all-recipe/fault endurance test or visual screenshot
review of the dashboard. Camera and robot behavior were verified headlessly;
dashboard changes were checked with the JavaScript rendering harness.

## Change Inventory

Added: `maintenance/{features,telemetry,ml,monitor}.py`,
`analytics/maintenance_experiment.py`, `config/maintenance.yaml`,
`scripts/{train_health_model,demo_machine_health}.py`,
`tests/test_ml_maintenance.py`, and this verification document.

Modified: `reconfactory/{config,models,stations,scheduler,supervisor,amr_transport,logger}.py`,
`app/main.py`, `analytics/{metrics,reports}.py`,
`scripts/{generate_sensor_data,run_experiment}.py`, `frontend/{app.js,styles.css}`,
`tests/frontend_movement.test.js`, the ROS factory `supervisor_node.py`,
`requirements.txt`, `.gitignore`, README and architecture/API/database/ROS/maintenance docs.
The original `maintenance/health.py`, vision algorithms, Nav2 configuration and
fault detector remain unchanged. No datasets or model binaries are committed.
