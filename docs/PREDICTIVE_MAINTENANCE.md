# Predictive Maintenance

The first predictive-maintenance layer is implemented as a rule-based baseline in `maintenance/health.py`.

## Signals

- Temperature
- Vibration
- Current draw

## Health Score

The health score is normalized from `0.0` to `1.0`.

- `healthy`: no action required
- `watch`: monitor the trend
- `warning`: plan maintenance
- `critical`: schedule immediate maintenance before more work

The dashboard machine cards show each machine's health percentage and maintenance status.

## Synthetic Sensor Data

```bash
python scripts/generate_sensor_data.py
```

## Recovery Comparison

```bash
python scripts/run_experiment.py
```

Output:

```text
data/generated_reports/recovery_comparison.json
```

## Future ML Extension

The generated sensor data can support:

- Isolation Forest
- One-class SVM
- Autoencoder
- Forecasting model for temperature and vibration trend
