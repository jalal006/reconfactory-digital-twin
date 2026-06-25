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

## WebSocket

```text
ws://127.0.0.1:8000/ws
```

Streams the same snapshot returned by `/api/status`.
