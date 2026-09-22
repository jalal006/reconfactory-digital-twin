# Database Schema

Predictive maintenance uses the existing schema: machine snapshot `data_json`
contains `machine_health`; `machine_health_changed` and `predictive_reroute`
events persist source, scores and routing reasons in event `data_json`.
Maintenance warning rows are written on status transitions instead of every
sample. Event CSV exports now include `data_json` for offline analysis.

SQLite logging is implemented in `reconfactory.logger.DataLogger`.

## Tables

### `events`

Stores operator actions, scheduling decisions, product events, fault detections, and recovery decisions.
Vision events include inspection metadata in `data_json`, such as source,
detected color, detected shape, area ratio, confidence, frame count, and camera
inspection latency.

### `products`

Stores the latest known state of each product. The `data_json` column contains the full serialized product object, including route history.

### `machine_snapshots`

Stores time-series machine status snapshots for analytics and later utilization reports.

### `faults`

Stores diagnosed fault records.

### `recovery_actions`

Stores rerouting and pause actions that were produced after a fault.

## Report Export

```bash
python scripts/export_report.py
```

The script exports event history to:

```text
data/generated_reports/events.csv
```
