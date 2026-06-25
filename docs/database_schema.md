# Database Schema

SQLite logging is implemented in `reconfactory.logger.DataLogger`.

## Tables

### `events`

Stores operator actions, scheduling decisions, product events, fault detections, and recovery decisions.

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
