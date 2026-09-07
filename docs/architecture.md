# Architecture

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
