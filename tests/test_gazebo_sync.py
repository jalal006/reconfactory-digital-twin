from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC_PATH = ROOT / "gazebo_fallback" / "scripts" / "sync_backend_to_gazebo.py"


def load_sync_module():
    spec = importlib.util.spec_from_file_location("gazebo_sync", SYNC_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_product_sdf_contains_expected_model_and_material() -> None:
    sync = load_sync_module()

    sdf = sync.product_sdf("rf_product_P_00001", "red_block")

    assert '<model name="rf_product_P_00001">' in sdf
    assert "<static>false</static>" in sdf
    assert "<gravity>false</gravity>" in sdf
    assert "<kinematic>true</kinematic>" in sdf
    assert "<box><size>0.40 0.40 0.36</size></box>" in sdf
    assert "1.000 0.080 0.080 1.000" in sdf


def test_product_target_moves_paused_product_to_recovery_buffer() -> None:
    sync = load_sync_module()
    bridge = sync.GazeboSync(
        backend_url="http://127.0.0.1:8000",
        world="reconfactory_world",
        interval=0.18,
        dry_run=True,
    )

    pose = bridge.product_target(
        {
            "product_id": "P-00001",
            "product_type": "red_block",
            "status": "paused",
            "current_location": "station_a",
            "assigned_station": "station_a",
        },
        0,
    )

    assert abs(pose.x - sync.LAYOUT["recovery_buffer"][0]) < 0.25
    assert abs(pose.y - sync.LAYOUT["recovery_buffer"][1]) < 0.25


def test_input_product_target_is_on_visible_conveyor() -> None:
    sync = load_sync_module()
    bridge = sync.GazeboSync(
        backend_url="http://127.0.0.1:8000",
        world="reconfactory_world",
        interval=0.08,
        dry_run=True,
    )

    pose = bridge.product_target(
        {
            "product_id": "P-00001",
            "product_type": "red_block",
            "status": "waiting",
            "current_location": "input_queue",
            "assigned_station": None,
        },
        0,
    )

    assert pose.x > 0.1
    assert pose.z >= 0.34


def test_new_product_assigned_ahead_starts_from_input_path() -> None:
    sync = load_sync_module()
    bridge = sync.GazeboSync(
        backend_url="http://127.0.0.1:8000",
        world="reconfactory_world",
        interval=0.04,
        dry_run=True,
    )

    bridge.sync_products(
        {
            "tick": 3,
            "products": [
                {
                    "product_id": "P-00001",
                    "product_type": "red_block",
                    "status": "processing",
                    "current_location": "station_a",
                    "assigned_station": "station_a",
                }
            ],
        }
    )

    path = bridge.product_paths["rf_product_P_00001"]
    assert abs(path[0].x - sync.LAYOUT["input_queue"][0]) < 0.01
    assert abs(path[-1].x - sync.LAYOUT["station_a"][0]) < 0.01
    assert 1.1 <= bridge.product_path_duration["rf_product_P_00001"] <= 2.5
    assert len(path) > 40
    assert max(point.y for point in path) <= sync.LAYOUT["station_a"][1] + 0.04
    assert min(point.y for point in path) >= -0.04


def test_backend_route_history_prevents_station_skips() -> None:
    sync = load_sync_module()
    bridge = sync.GazeboSync(
        backend_url="http://127.0.0.1:8000",
        world="reconfactory_world",
        interval=0.04,
        dry_run=True,
    )

    bridge.sync_product_targets(
        {
            "tick": 5,
            "products": [
                {
                    "product_id": "P-00001",
                    "product_type": "red_block",
                    "status": "processing",
                    "current_location": "station_a",
                    "assigned_station": "station_a",
                    "route": ["input_queue", "vision", "processing_buffer", "station_a"],
                }
            ],
        }
    )

    model_name = "rf_product_P_00001"
    assert bridge.product_destinations[model_name] == "vision"
    assert bridge.product_pending_destinations[model_name] == ["processing_buffer", "station_a"]
    assert abs(bridge.product_paths[model_name][-1].x - sync.LAYOUT["vision"][0]) < 0.01


def test_station_to_quality_route_stays_on_branch_centerline() -> None:
    sync = load_sync_module()
    bridge = sync.GazeboSync(
        backend_url="http://127.0.0.1:8000",
        world="reconfactory_world",
        interval=0.04,
        dry_run=True,
    )

    path = bridge.transition_path(
        "station_a",
        "quality",
        sync.pose_from_tuple(sync.LAYOUT["station_a"]),
        sync.pose_from_tuple(sync.LAYOUT["quality"]),
    )

    assert len(path) > 45
    assert max(point.y for point in path) <= sync.LAYOUT["station_a"][1] + 0.04
    assert min(point.y for point in path) >= -0.04


def test_early_backend_location_change_is_queued_until_robot_arrives() -> None:
    sync = load_sync_module()
    bridge = sync.GazeboSync(
        backend_url="http://127.0.0.1:8000",
        world="reconfactory_world",
        interval=0.04,
        dry_run=True,
    )
    product = {
        "product_id": "P-00001",
        "product_type": "red_block",
        "status": "processing",
        "current_location": "station_a",
        "assigned_station": "station_a",
    }
    bridge.sync_product_targets({"tick": 3, "products": [product]})

    product = {
        **product,
        "current_location": "quality",
        "assigned_station": "quality",
    }
    bridge.sync_product_targets({"tick": 4, "products": [product]})

    model_name = "rf_product_P_00001"
    assert bridge.product_destinations[model_name] == "station_a"
    assert bridge.product_pending_destinations[model_name] == ["quality"]
    assert abs(bridge.product_paths[model_name][-1].x - sync.LAYOUT["station_a"][0]) < 0.01


def test_pending_destination_starts_after_robot_reaches_current_destination() -> None:
    sync = load_sync_module()
    bridge = sync.GazeboSync(
        backend_url="http://127.0.0.1:8000",
        world="reconfactory_world",
        interval=0.04,
        dry_run=True,
    )
    product = {
        "product_id": "P-00001",
        "product_type": "red_block",
        "status": "processing",
        "current_location": "station_a",
        "assigned_station": "station_a",
    }
    bridge.sync_product_targets({"tick": 3, "products": [product]})
    model_name = "rf_product_P_00001"
    bridge.product_pending_destinations[model_name] = ["quality"]
    bridge.product_poses[model_name] = bridge.product_paths[model_name][-1]
    bridge.product_waypoint_index[model_name] = len(bridge.product_paths[model_name]) - 1

    bridge.advance_products()

    assert bridge.product_locations[model_name] == "station_a"
    assert bridge.product_destinations[model_name] == "station_a"
    assert model_name in bridge.product_arrival_settle_until
    assert model_name not in bridge.product_dwell_location

    bridge.product_arrival_settle_until[model_name] = 0.0
    bridge.advance_products()

    assert bridge.product_dwell_location[model_name] == "station_a"

    bridge.product_dwell_until[model_name] = 0.0
    bridge.advance_products()

    assert bridge.product_destinations[model_name] == "quality"
    assert model_name not in bridge.product_pending_destinations
    assert abs(bridge.product_paths[model_name][-1].x - sync.LAYOUT["quality"][0]) < 0.01


def test_paused_state_does_not_start_new_product_motion() -> None:
    sync = load_sync_module()
    bridge = sync.GazeboSync(
        backend_url="http://127.0.0.1:8000",
        world="reconfactory_world",
        interval=0.04,
        dry_run=True,
    )
    product = {
        "product_id": "P-00001",
        "product_type": "green_component",
        "status": "processing",
        "current_location": "vision",
        "assigned_station": "vision",
        "route": ["input_queue", "vision"],
    }

    bridge.sync_product_targets({"running": False, "tick": 1, "products": [product]})

    model_name = "rf_product_P_00001"
    assert bridge.product_locations[model_name] == "input_queue"
    assert bridge.product_destinations[model_name] == "input_queue"
    assert model_name not in bridge.product_paths
    assert not bridge.active_transport_routes()


def test_paused_state_finishes_current_leg_without_starting_pending_leg() -> None:
    sync = load_sync_module()
    bridge = sync.GazeboSync(
        backend_url="http://127.0.0.1:8000",
        world="reconfactory_world",
        interval=0.04,
        dry_run=True,
    )
    model_name = "rf_product_P_00001"
    start = sync.pose_from_tuple(sync.LAYOUT["station_a"])
    target = sync.pose_from_tuple(sync.LAYOUT["quality_buffer"])
    bridge.spawned_products.add(model_name)
    bridge.product_ids_by_model[model_name] = "P-00001"
    bridge.product_poses[model_name] = start
    bridge.product_locations[model_name] = "station_a"
    bridge.product_pending_destinations[model_name] = ["quality"]
    bridge.set_product_path(
        model_name,
        bridge.transition_path("station_a", "quality_buffer", start, target),
        {"running": True},
        destination="quality_buffer",
        route_name="station_a_to_quality_buffer",
    )
    bridge.product_path_start[model_name] = 0.0
    bridge.product_path_duration[model_name] = 0.0
    bridge.latest_state = {"running": False}

    bridge.advance_products()

    assert bridge.product_locations[model_name] == "quality_buffer"
    assert bridge.product_destinations[model_name] == "quality_buffer"
    assert bridge.product_pending_destinations[model_name] == ["quality"]
    assert model_name not in bridge.product_arrival_settle_until
    assert model_name not in bridge.product_dwell_location


def test_transition_duration_pads_for_measured_gazebo_latency() -> None:
    sync = load_sync_module()
    bridge = sync.GazeboSync(
        backend_url="http://127.0.0.1:8000",
        world="reconfactory_world",
        interval=0.04,
        dry_run=True,
    )
    state = {
        "simulation_speed": 1.0,
        "visual_sync": {
            "min_transition_ms": 1100,
            "max_transition_ms": 2500,
            "gazebo_meters_per_second": 1.85,
            "gazebo_latency_multiplier": 4.0,
        },
    }
    path = [sync.Pose(0, 0, 0), sync.Pose(1.85, 0, 0)]

    baseline = bridge.transition_duration(path, state)
    bridge.command_latency_ema_s = 0.2
    padded = bridge.transition_duration(path, state)

    assert abs(baseline - 1.1) < 0.001
    assert baseline < padded <= 2.5


def test_advance_toward_caps_large_position_jump() -> None:
    sync = load_sync_module()

    current = sync.Pose(0, 0, 0)
    desired = sync.Pose(5, 0, 0)
    next_pose = sync.advance_toward(current, desired, max_distance=0.2)

    assert 0.19 <= next_pose.x <= 0.21
    assert next_pose.x < desired.x


def test_transport_phase_reports_active_route_without_moving_product() -> None:
    sync = load_sync_module()
    bridge = sync.GazeboSync(
        backend_url="http://127.0.0.1:8000",
        world="reconfactory_world",
        interval=0.04,
        dry_run=True,
    )
    product = {
        "product_id": "P-00001",
        "product_type": "red_block",
        "status": "processing",
        "current_location": "vision",
        "assigned_station": "vision",
    }

    bridge.sync_product_targets({"tick": 1, "products": [product]})
    model_name = "rf_product_P_00001"
    start_pose = bridge.product_poses[model_name]
    bridge.advance_products()

    assert "input_to_vision" in bridge.active_transport_routes()
    assert bridge.product_poses[model_name] == start_pose


def test_vision_to_buffer_uses_its_own_route_indicator() -> None:
    sync = load_sync_module()
    bridge = sync.GazeboSync(
        backend_url="http://127.0.0.1:8000",
        world="reconfactory_world",
        interval=0.04,
        dry_run=True,
    )

    assert bridge.route_name("vision", "processing_buffer") == "vision_to_buffer"
    assert bridge.route_name("vision", "processing_buffer") != "input_to_vision"


def test_buffer_connector_routes_use_exact_indicators() -> None:
    sync = load_sync_module()
    bridge = sync.GazeboSync(
        backend_url="http://127.0.0.1:8000",
        world="reconfactory_world",
        interval=0.04,
        dry_run=True,
    )

    assert (
        bridge.route_name("processing_buffer", "station_a") == "processing_buffer_to_station_a"
    )
    assert (
        bridge.route_name("processing_buffer", "station_b") == "processing_buffer_to_station_b"
    )
    assert bridge.route_name("station_a", "quality_buffer") == "station_a_to_quality_buffer"
    assert bridge.route_name("station_b", "quality_buffer") == "station_b_to_quality_buffer"
    assert bridge.route_name("quality_buffer", "quality") == "quality_buffer_to_quality"


def test_new_product_route_clears_previous_route_hold() -> None:
    sync = load_sync_module()
    bridge = sync.GazeboSync(
        backend_url="http://127.0.0.1:8000",
        world="reconfactory_world",
        interval=0.04,
        dry_run=True,
    )
    model_name = "rf_product_P_00001"
    bridge.set_product_path(
        model_name,
        [
            sync.pose_from_tuple(sync.LAYOUT["input_queue"]),
            sync.pose_from_tuple(sync.LAYOUT["vision"]),
        ],
        {},
        destination="vision",
        route_name="input_to_vision",
    )
    bridge.set_product_path(
        model_name,
        [
            sync.pose_from_tuple(sync.LAYOUT["vision"]),
            sync.pose_from_tuple(sync.LAYOUT["station_a"]),
        ],
        {},
        destination="station_a",
        route_name="vision_to_station_a",
    )

    assert "input_to_vision" not in bridge.active_route_until
    assert "vision_to_station_a" in bridge.active_route_until


def test_transport_phase_snaps_product_to_destination_after_timer() -> None:
    sync = load_sync_module()
    bridge = sync.GazeboSync(
        backend_url="http://127.0.0.1:8000",
        world="reconfactory_world",
        interval=0.04,
        dry_run=True,
    )
    product = {
        "product_id": "P-00001",
        "product_type": "red_block",
        "status": "processing",
        "current_location": "vision",
        "assigned_station": "vision",
    }

    bridge.sync_product_targets({"tick": 1, "products": [product]})
    model_name = "rf_product_P_00001"
    bridge.product_path_start[model_name] = 0.0
    bridge.product_path_duration[model_name] = 0.0
    bridge.advance_products()

    assert bridge.path_completed(model_name)
    assert abs(bridge.product_poses[model_name].x - sync.LAYOUT["vision"][0]) < 0.01
    assert model_name in bridge.product_arrival_settle_until


def test_status_updates_prioritize_faults_over_initial_idle_beacons() -> None:
    sync = load_sync_module()
    bridge = sync.GazeboSync(
        backend_url="http://127.0.0.1:8000",
        world="reconfactory_world",
        interval=0.04,
        dry_run=True,
    )

    state = {
        "running": True,
        "queues": {"input": []},
        "products": [],
        "events": [],
        "machines": [
            {"machine_id": "conveyor_main", "state": "running", "current_product_id": None},
            {"machine_id": "vision", "state": "idle", "current_product_id": None},
            {"machine_id": "station_a", "state": "fault", "current_product_id": None},
            {"machine_id": "station_b", "state": "idle", "current_product_id": None},
            {"machine_id": "quality", "state": "idle", "current_product_id": None},
        ],
    }

    bridge.sync_status_lights(state, max_updates=1)

    assert bridge.status_states == {"station_a": "fault"}


def test_machine_indicator_waits_for_gazebo_robot_arrival() -> None:
    sync = load_sync_module()
    bridge = sync.GazeboSync(
        backend_url="http://127.0.0.1:8000",
        world="reconfactory_world",
        interval=0.04,
        dry_run=True,
    )
    machines = {
        "station_a": {
            "machine_id": "station_a",
            "state": "running",
            "current_product_id": "P-00001",
        }
    }

    status = bridge.indicator_status("station_a", {}, machines, {}, set(), 0)

    assert status == "idle"


def test_machine_indicator_processes_only_during_gazebo_dwell() -> None:
    sync = load_sync_module()
    bridge = sync.GazeboSync(
        backend_url="http://127.0.0.1:8000",
        world="reconfactory_world",
        interval=0.04,
        dry_run=True,
    )

    status = bridge.indicator_status("station_a", {}, {}, {"station_a": 1}, {"station_a"}, 0)

    assert status == "processing"


def test_active_transport_locations_reports_current_destination() -> None:
    sync = load_sync_module()
    bridge = sync.GazeboSync(
        backend_url="http://127.0.0.1:8000",
        world="reconfactory_world",
        interval=0.04,
        dry_run=True,
    )
    model_name = "rf_product_P_00001"
    bridge.spawned_products.add(model_name)
    bridge.product_poses[model_name] = sync.pose_from_tuple(sync.LAYOUT["vision"])
    bridge.product_destinations[model_name] = "station_a"
    bridge.product_paths[model_name] = [
        sync.pose_from_tuple(sync.LAYOUT["vision"]),
        sync.pose_from_tuple(sync.LAYOUT["station_a"]),
    ]
    bridge.product_waypoint_index[model_name] = 1
    bridge.product_path_start[model_name] = time.monotonic()
    bridge.product_path_duration[model_name] = 2.0

    assert bridge.active_transport_locations() == {"station_a"}


def test_route_indicators_hold_after_short_transport_finishes() -> None:
    sync = load_sync_module()
    bridge = sync.GazeboSync(
        backend_url="http://127.0.0.1:8000",
        world="reconfactory_world",
        interval=0.04,
        dry_run=True,
    )
    model_name = "rf_product_P_00001"
    target = sync.pose_from_tuple(sync.LAYOUT["station_a"])
    bridge.spawned_products.add(model_name)
    bridge.product_poses[model_name] = target
    bridge.product_waypoint_index[model_name] = 1
    bridge.set_product_path(
        model_name,
        [sync.pose_from_tuple(sync.LAYOUT["vision"]), target],
        {"visual_sync": {"gazebo_min_transition_ms": 50, "gazebo_max_transition_ms": 50}},
        destination="station_a",
        route_name="vision_to_station_a",
    )
    bridge.product_poses[model_name] = target
    bridge.product_waypoint_index[model_name] = 1

    assert "vision_to_station_a" in bridge.active_transport_routes()
    assert "station_a" in bridge.active_transport_locations()


def test_status_light_sdf_uses_fault_emissive_color() -> None:
    sync = load_sync_module()

    sdf = sync.status_light_sdf("rf_status_station_a", "fault")

    assert '<model name="rf_status_station_a">' in sdf
    assert "1.000 0.060 0.060 1.000" in sdf
