# Architecture

## Predictive Health

Machine telemetry is sampled once per supervisor tick into bounded per-machine
histories. A shared rolling feature pipeline feeds the opt-in Isolation Forest;
the rule baseline remains the default and the explicit warmup fallback.
The scheduler applies configurable risk penalties only after capability and
availability checks. The supervisor records changed assignments and health-state
transitions using existing event persistence. Machine snapshot JSON feeds the
dashboard, WebSocket and ROS health topic. ML imports are deferred so system-Python
ROS camera nodes do not need backend scikit-learn/joblib packages.
See [Predictive Maintenance](PREDICTIVE_MAINTENANCE.md).

ReConFactory is organized around a single top-level `FactorySupervisor`. The supervisor owns station controllers, product tracking, scheduling, fault detection, diagnosis, recovery, and persistence.

## Runtime Flow

```text
Browser dashboard
  -> FastAPI command endpoint
  -> FactorySupervisor
  -> ProductTracker / ProductionScheduler / FaultDetector
  -> StationController instances
  -> SQLite DataLogger
  -> WebSocket snapshots back to dashboard
```

## Core Modules

- `reconfactory.models`: enums and dataclasses for products, machines, faults, events, and recovery actions.
- `reconfactory.state_machine`: allowed machine state transitions.
- `reconfactory.stations`: station controller simulation, sensors, assignment, ticking, fault and recovery behavior.
- `reconfactory.tracker`: product identity, route, status, location, and quality tracking.
- `reconfactory.scheduler`: station capability and availability selection.
- `reconfactory.faults`: threshold-based detection and rule-based diagnosis.
- `reconfactory.reconfiguration`: recovery action creation and audit summaries.
- `reconfactory.logger`: SQLite persistence.
- `reconfactory.supervisor`: orchestration and public control surface.

## Machine State Model

```text
OFFLINE -> STARTING -> IDLE -> RUNNING -> IDLE
RUNNING -> FAULT -> RECOVERING -> IDLE
FAULT -> MAINTENANCE -> RECOVERING -> IDLE
ANY active state -> EMERGENCY_STOP
```

Invalid transitions raise an exception in tests and during development.

## Recovery Policy

When a machine fails:

1. The station is marked `fault`.
2. The diagnosis engine creates a fault record.
3. The failed station is removed from scheduling because `healthy == false`.
4. If a product was inside the station, it is released to the recovery buffer.
5. Compatible work is assigned to an alternative healthy station when available.
6. Products with no safe route are paused.
7. Fault and recovery records are stored.

## Advanced Integration Layers

The core factory logic stays in Python/FastAPI. Advanced simulators and industrial interfaces subscribe to or poll the same state instead of duplicating scheduling logic.

```text
FastAPI backend
  -> Browser Canvas dashboard
  -> OpenCV inspection
  -> ROS 2 bridge nodes
  -> Gazebo visualization
  -> OPC UA industrial clients
```

This keeps the scheduler, fault detector, diagnosis engine, and recovery manager as the single source of truth.

## Gazebo Camera Perception

Gazebo camera mode adds a sensor feedback path without moving factory authority
out of the supervisor:

```text
FactorySupervisor product state
  -> Gazebo product pose
  -> Gazebo RGB camera at vision station
  -> ros_gz_bridge sensor_msgs/Image
  -> /reconfactory_vision_inspector
  -> OpenCV classification and 5-frame aggregation
  -> /api/vision/result
  -> FactorySupervisor quality/routing decision
```

The ROS 2 vision node performs perception only. It does not accept, reject,
route, or persist products by itself.

## Optional AMR Transport

`FactorySupervisor` owns a ROS-independent `FactoryTransport` delivery gate when
`TRANSPORT_MODE=amr`. It asks the existing `ProductionScheduler` for a compatible,
unoccupied station, records a `TransportRequest`, and keeps the product at its
origin with `in_transit` status. The AMR manager navigates to pickup and then
delivery using two standard Nav2 actions. Only a validated `delivered` status
changes product location and permits station processing. Final output delivery
is gated in the same way. Duplicate/stale results cannot advance production.

The existing Gazebo sync process is the sole product-pose writer: it carries
cargo above the robot during the delivery phase, then places it at the confirmed
station. It never teleports the robot. The browser displays confirmed station
transitions, not predictive conveyor transfers, in this mode.

See [AMR Navigation](AMR_NAVIGATION.md) for TF ownership, task contracts, failure
handling, static-map generation and verification.

Hard destination faults invalidate the current mission without moving its product.
The AMR manager cancels Nav2, waits for a terminal result plus stopped odometry,
and reports cancellation. Only then does the supervisor ask the existing scheduler
for a replacement. Loaded tasks skip pickup and Nav2 plans from the current pose.
No alternate means a held payload, not successful delivery. Health scores influence
replacement choice but never trigger cancellation. See
[Fault-Aware Replanning](FAULT_AWARE_REPLANNING.md) for contracts and races.

```mermaid
sequenceDiagram
    participant S as FactorySupervisor
    participant R as ProductionScheduler
    participant M as AMR Manager
    participant N as Nav2
    S->>M: Invalidate destination; cancel_requested
    M->>N: Cancel existing NavigateToPose
    N-->>M: Terminal action result
    Note over M: Require fresh stopped odometry
    M-->>S: cancelled, payload retained
    S->>R: Select compatible available station
    alt Replacement available
        R-->>S: Replacement destination
        S->>M: Linked task, payload_loaded=true
        M->>N: NavigateToPose from current pose
        N-->>M: Success
        M-->>S: delivered
        Note over S: Move product; start processing
    else No alternative
        Note over S,M: Hold payload; await station recovery
    end
```

This diagram describes a loaded delivery interrupted by a hard destination fault.
Before pickup, a replacement still needs its pickup leg. Cancellation rejection or
lost goal ownership blocks automatic replacement. ML risk changes alone do not
enter this sequence; they only affect the existing scheduler's station selection.
