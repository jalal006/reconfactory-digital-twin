# API

Base URL when running locally:

```text
http://127.0.0.1:8000
```

## Status

```http
GET /api/status
```

Returns the full factory snapshot: machines, products, queues, events, faults, recovery actions, recipes, and metrics.

## Start And Stop

```http
POST /api/start
POST /api/stop
```

## Maintenance

`GET /api/maintenance` returns `mode`, `scheduling_enabled` and `machines` health
predictions. `/api/status` and WebSocket snapshots include each machine's
`machine_health`, plus `stats.predictive_diversions`.

`POST /api/telemetry` accepts simulated `machine_id`, `temperature_c`,
`vibration_mm_s` and `current_a`. Numeric values must be finite and nonnegative;
an unknown machine returns 404. The next running tick samples the values before
assignment. This local demo endpoint is not a hardware or authenticated public
telemetry gateway. See [Predictive Maintenance](PREDICTIVE_MAINTENANCE.md).

## AMR Transport

With `TRANSPORT_MODE=amr`, the supervisor remains the production authority.
The AMR manager uses these integration endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /api/transport` | Mode, running state, readiness, active task and robot pose |
| `POST /api/transport/heartbeat` | Report Nav2/localization readiness and optional finite robot pose |
| `POST /api/transport/status` | Report an active task's pickup/delivery progress |

Status fields are `task_id`, `product_id`, `destination`, `status`, `phase`,
`navigation_time_s`, and optional `failure_reason`. Status is one of `accepted`,
`navigating`, `delivered`, `failed`, or `cancelled`; phase is `pickup` or
`delivery`. Invalid task transitions return HTTP 409. Writes return HTTP 409
when AMR mode is disabled; invalid request fields return HTTP 422.

These endpoints are for the trusted local simulation manager, not manual
delivery shortcuts. The manager reports delivery only after Nav2 succeeds;
products remain at their last confirmed station until then. Stop cancels active
navigation in AMR mode. Hard destination faults request cancellation and wait for
the manager to confirm the old action ended and the robot stopped before replanning.
Other failed/cancelled tasks remain held for operator recovery; uncertain navigation
requires inspection and stack restart, not merely pressing Reset.

The active task in `GET /api/transport` and WebSocket snapshots additionally exposes
`payload_loaded`, `replan_state`, `replan_reason`, `fault_id`, `original_destination`,
`supersedes_task_id`, `cancel_latency_s` and `replan_latency_s`. Replan states are
`cancelling`, `awaiting_replan`, or `blocked_transport`; null means no active replan
state. These fields are supervisor-owned, not extra writable status fields.
A loaded replacement starts with phase `delivery` and skips pickup. With no available
compatible station, the old cancelled task remains active and retains its payload.
An invalidated task cannot deliver; stale or invalid transitions return HTTP 409.
See [AMR Navigation](AMR_NAVIGATION.md) for contracts and limitations.

## Add Product

```http
POST /api/products
Content-Type: application/json

{
  "product_type": "red_block",
  "defect_flags": []
}
```

Supported product types:

- `red_block`
- `blue_cylinder`
- `green_component`

Supported defect flags:

- `wrong_colour`
- `wrong_shape`
- `missing_part`
- `quality_defect`
- `unidentified`

## Manual Tick

```http
POST /api/tick
Content-Type: application/json

{
  "steps": 1
}
```

The dashboard also runs an automatic tick loop while production is started.

## Inject Fault

```http
POST /api/faults
Content-Type: application/json

{
  "machine_id": "station_a",
  "fault_type": "overheat",
  "reason": "Dashboard fault injection"
}
```

Fault types:

- `overheat`
- `jam`
- `sensor_failure`
- `camera_failure`
- `timeout`
- `communication_loss`
- `unknown`

Machine IDs:

- `conveyor_main`
- `vision`
- `station_a`
- `station_b`
- `quality`

## Recover Machine

```http
POST /api/recover
Content-Type: application/json

{
  "machine_id": "station_a"
}
```

## Vision Result

```http
POST /api/vision/result
Content-Type: application/json

{
  "product_id": "P-00001",
  "source": "gazebo_camera",
  "accepted": true,
  "detected_color": "red",
  "detected_shape": "block",
  "area_ratio": 0.94,
  "missing_material": false,
  "confidence": 0.93,
  "frame_count": 5,
  "inspection_latency_ms": 180.0
}
```

Used by the ROS 2 Gazebo camera inspector. The supervisor accepts the result
only when `product_id` matches the product currently waiting at the vision
station.

## AMR Transport And Energy

`GET /api/transport` exposes transport mode, readiness, active task, localized
robot pose and the supervisor-owned `energy` object. The same energy object is
included in `GET /api/status` and WebSocket snapshots.

Energy fields include `capacity_wh`, `remaining_wh`, `state_of_charge` (0..1),
`energy_consumed_wh`, `energy_charged_wh`, `is_charging`, `state`, `reason`,
`estimated_energy_wh`, `deferred_transport`, reserve/target SOC, `charge_cycles`
and `charging_seconds`. Units and assumptions are documented in
[Energy-Aware AMR](ENERGY_AWARE_AMR.md).

`POST /api/transport/heartbeat` is the AMR manager's integration endpoint. In
addition to `ready` and `robot_pose`, it accepts optional cumulative `motion`:

```json
{
  "session_id": "manager-session-id",
  "sequence": 42,
  "elapsed_s": 10.0,
  "distance_m": 2.5,
  "rotation_rad": 0.7
}
```

These fields belong inside the heartbeat's `motion` object. Counters must be
finite, nonnegative and nondecreasing within a session. Replayed sequence numbers
do not consume energy twice. The backend computes battery state; callers do not
set SOC or claim delivery through telemetry.

`POST /api/transport/status` still controls acknowledged transport transitions.
`mission_type=charge` shares the existing mission authority, does not carry a
product, and cannot charge until successful navigation is confirmed at the dock.
Transport event JSON includes estimated and actual mission energy without a
destructive database schema change.

## WebSocket

```text
ws://127.0.0.1:8000/ws
```

Streams the same snapshot returned by `/api/status`.
