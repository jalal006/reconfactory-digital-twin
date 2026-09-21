"""Transport contracts and delivery gating without ROS, Gazebo or Nav2."""

import json
import math
import sys
import time
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from reconfactory import FactorySupervisor
from reconfactory.models import FaultType, ProductStatus
from reconfactory.transport import (
    TaskRegistry,
    TransportRequest,
    load_station_goals,
    task_timeout_s,
)
from scripts.generate_amr_map import (
    layout_config,
    lidar_boxes,
    obstacle_boxes,
    occupied,
    prepare_world,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ros2_ws/src/reconfactory_amr"))
from reconfactory_amr.navigation import NavigationRunner  # noqa: E402

STATIONS = load_station_goals(ROOT / "ros2_ws/src/reconfactory_amr/config/stations.yaml")


def request():
    return TransportRequest("P-test", "input_queue", "vision")


def deliver(factory):
    task = factory.transport.active
    for status, phase in [
        ("accepted", "pickup"),
        ("navigating", "pickup"),
        ("navigating", "delivery"),
        ("delivered", "delivery"),
    ]:
        factory.transport.receive({**task.to_dict(), "status": status, "phase": phase})


def test_station_poses_have_robot_clearance():
    boxes = obstacle_boxes(prepare_world())
    floor = layout_config()["floor"]
    cx, cy = floor["center"]
    width, height = floor["size"]
    config = yaml.safe_load(
        (ROOT / "ros2_ws/src/reconfactory_amr/config/nav2.yaml").read_text()
    )
    radius = config["global_costmap"]["global_costmap"]["ros__parameters"]["robot_radius"]
    for name, pose in STATIONS.items():
        for angle in range(0, 360, 10):
            x = pose["x"] + radius * math.cos(math.radians(angle))
            y = pose["y"] + radius * math.sin(math.radians(angle))
            assert not occupied(x, y, boxes), name
            assert cx - width / 2 < x < cx + width / 2, name
            assert cy - height / 2 < y < cy + height / 2, name


def test_localization_map_excludes_invisible_collision_envelopes():
    world = prepare_world()
    navigation, localization = obstacle_boxes(world), lidar_boxes(world)
    assert occupied(4.0, -3.54, navigation)
    assert not occupied(4.0, -3.54, localization)  # Rail is above the scan plane.
    assert occupied(-2.5, 0.0, localization)  # Actual wall remains observable.
    assert not occupied(4.0, -4.5, localization)  # Floor edge is not a LiDAR wall.


def test_workcell_docks_have_direct_clear_transfer_corridors():
    boxes = obstacle_boxes(prepare_world())
    pairs = [
        ("vision", "station_a"),
        ("vision", "station_b"),
        ("station_a", "quality"),
        ("station_b", "quality"),
        ("quality", "accepted_output"),
        ("quality", "reject_output"),
    ]
    for origin, destination in pairs:
        a, b = STATIONS[origin], STATIONS[destination]
        for step in range(101):
            t = step / 100
            x, y = a["x"] + t * (b["x"] - a["x"]), a["y"] + t * (b["y"] - a["y"])
            for angle in range(0, 360, 15):
                # Extra clearance beyond the 0.31 m robot radius.
                assert not occupied(
                    x + 0.4 * math.cos(math.radians(angle)),
                    y + 0.4 * math.sin(math.radians(angle)),
                    boxes,
                ), (origin, destination)


def test_amr_layout_keeps_camera_attached_and_original_world_unchanged():
    from xml.etree import ElementTree as ET

    original = ET.parse(ROOT / "gazebo_fallback/worlds/reconfactory.world.sdf")
    generated = prepare_world()
    query = "world/model[@name='vision_camera_station']"
    before = original.getroot().find(query)
    after = generated.getroot().find(query)
    assert before.findtext("pose") != after.findtext("pose")
    assert ET.tostring(before.find("link/sensor")) == ET.tostring(after.find("link/sensor"))
    assert original.getroot().find("world/model[@name='conveyor_input_to_vision']") is not None
    assert generated.getroot().find("world/model[@name='conveyor_input_to_vision']") is None


def test_nav2_costmaps_share_collision_envelopes_and_inflation():
    config = yaml.safe_load(
        (ROOT / "ros2_ws/src/reconfactory_amr/config/nav2.yaml").read_text()
    )
    controller = config["controller_server"]["ros__parameters"]["FollowPath"]
    assert (
        controller["plugin"]
        == "nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController"
    )
    assert controller["use_collision_detection"] is True
    assert controller["use_cost_regulated_linear_velocity_scaling"] is True
    for name in ("global_costmap", "local_costmap"):
        costmap = config[name][name]["ros__parameters"]
        assert {"static_layer", "obstacle_layer", "inflation_layer"}.issubset(
            costmap["plugins"]
        )
        assert costmap["robot_radius"] >= math.hypot(0.21, 0.21)
        assert costmap["inflation_layer"]["inflation_radius"] > costmap["robot_radius"]
        assert costmap["inflation_layer"]["cost_scaling_factor"] == 3.0
        assert controller["inflation_cost_scaling_factor"] == 3.0


def test_logical_docks_require_stopped_arrival_without_heading_spins():
    config = yaml.safe_load(
        (ROOT / "ros2_ws/src/reconfactory_amr/config/nav2.yaml").read_text()
    )
    parameters = config["controller_server"]["ros__parameters"]
    goal = parameters["goal_checker"]
    assert goal["plugin"] == "nav2_controller::StoppedGoalChecker"
    assert goal["xy_goal_tolerance"] == 0.12
    assert goal["stateful"] is False
    assert goal["yaw_goal_tolerance"] == math.pi
    assert goal["trans_stopped_velocity"] <= 0.05
    assert goal["rot_stopped_velocity"] <= 0.1
    assert parameters["FollowPath"]["stateful"] is False
    assert (
        parameters["FollowPath"]["min_approach_linear_velocity"]
        < goal["trans_stopped_velocity"]
    )
    assert (
        config["planner_server"]["ros__parameters"]["GridBased"][
            "use_final_approach_orientation"
        ]
        is True
    )


def test_navigation_speed_limits_fit_smoother_and_drive():
    from xml.etree import ElementTree as ET

    config = yaml.safe_load(
        (ROOT / "ros2_ws/src/reconfactory_amr/config/nav2.yaml").read_text()
    )
    controller = config["controller_server"]["ros__parameters"]["FollowPath"]
    smoother = config["velocity_smoother"]["ros__parameters"]
    robot = ET.parse(ROOT / "ros2_ws/src/reconfactory_amr/urdf/amr.urdf.xacro")
    drive = robot.getroot().find("gazebo/plugin[@name='gz::sim::systems::DiffDrive']")
    assert (
        0.25
        < controller["desired_linear_vel"]
        <= smoother["max_velocity"][0]
        <= float(drive.findtext("max_linear_velocity"))
    )
    assert (
        controller["rotate_to_heading_angular_vel"]
        <= smoother["max_velocity"][2]
        <= float(drive.findtext("max_angular_velocity"))
    )
    assert smoother["max_accel"][0] <= float(drive.findtext("max_linear_acceleration"))
    assert controller["max_angular_accel"] <= smoother["max_accel"][2]


def test_nav2_action_acknowledgement_tolerates_scheduling_jitter():
    config = yaml.safe_load(
        (ROOT / "ros2_ws/src/reconfactory_amr/config/nav2.yaml").read_text()
    )
    assert 200 <= config["bt_navigator"]["ros__parameters"]["default_server_timeout"] <= 1000


def test_request_serialization_and_invalid_station():
    task = request()
    assert (
        TransportRequest.from_dict(json.loads(json.dumps(task.to_dict())), STATIONS).destination
        == "vision"
    )
    with pytest.raises(ValueError, match="Unknown"):
        TransportRequest.from_dict({**task.to_dict(), "destination": "absent"}, STATIONS)
    with pytest.raises(ValueError, match="Missing"):
        TransportRequest.from_dict({}, STATIONS)


def test_registry_duplicates_and_busy():
    registry = TaskRegistry(STATIONS)
    task = request()
    registry.receive(task.to_dict())
    with pytest.raises(ValueError, match="Duplicate"):
        registry.receive(task.to_dict())
    with pytest.raises(ValueError, match="busy"):
        registry.receive(request().to_dict())


def test_status_order_and_identity():
    task = request()
    with pytest.raises(ValueError, match="phase"):
        task.update({**task.to_dict(), "status": "accepted", "phase": "delivery"})
    with pytest.raises(ValueError):
        task.update({**task.to_dict(), "status": "delivered"})
    with pytest.raises(ValueError):
        task.update({**task.to_dict(), "product_id": "wrong", "status": "accepted"})
    task.update({**task.to_dict(), "status": "accepted"})
    task.update({**task.to_dict(), "status": "navigating"})
    with pytest.raises(ValueError, match="pickup"):
        task.update({**task.to_dict(), "status": "delivered"})
    task.cancel_requested = True
    with pytest.raises(ValueError, match="cancellation"):
        task.update({**task.to_dict(), "status": "delivered"})


def test_supervisor_waits_for_delivery():
    f = FactorySupervisor(
        enable_database=False, transport_mode="amr", vision_source="synthetic"
    )
    p = f.create_product("red_block")
    f.start()
    f.tick(10)
    assert p.current_location == "input_queue"
    assert f.transport.active is None  # No runtime heartbeat: fail closed.
    f.transport.heartbeat(True)
    f.tick(10)
    assert p.status == ProductStatus.IN_TRANSIT
    assert p.current_location == "input_queue"
    assert f.stations["vision"].current_product_id is None
    deliver(f)
    assert p.current_location == "vision"
    assert p.status == ProductStatus.PROCESSING


@pytest.mark.parametrize("kind", ["red_block", "blue_cylinder", "green_component"])
@pytest.mark.parametrize("defects", [[], ["wrong_colour"], ["wrong_shape"], ["missing_part"]])
def test_all_recipes_finish_only_after_delivery(kind, defects):
    f = FactorySupervisor(
        enable_database=False, transport_mode="amr", vision_source="synthetic"
    )
    p = f.create_product(kind, defects)
    f.start()
    delivered = []
    for _ in range(150):
        f.transport.heartbeat(True)
        f.tick()
        if f.transport.active:
            delivered.append(f.transport.active.destination)
            assert p.current_location != f.transport.active.destination
            assert p.status == ProductStatus.IN_TRANSIT
            deliver(f)
        if f.is_idle():
            break
    assert p.status == (ProductStatus.REJECTED if defects else ProductStatus.COMPLETED)
    assert delivered[0] == "vision"
    assert delivered[-1] == ("reject_output" if defects else "accepted_output")
    assert not f.input_queue and not f.processing_queue and not f.quality_queue


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_failure_keeps_origin_and_blocks_next_task(status):
    f = FactorySupervisor(enable_database=False, transport_mode="amr")
    p = f.create_product("red_block")
    f.start()
    f.transport.heartbeat(True)
    f.tick()
    task = f.transport.active
    f.transport.receive({**task.to_dict(), "status": status, "failure_reason": "blocked"})
    f.tick(10)
    assert p.current_location == "input_queue"
    assert p.status == ProductStatus.PAUSED
    assert f.transport.active.task_id == task.task_id


def test_transport_watchdog():
    f = FactorySupervisor(enable_database=False, transport_mode="amr")
    p = f.create_product("red_block")
    f.start()
    f.transport.heartbeat(True)
    f.tick()
    f.transport.last_heartbeat = time.monotonic() - 11
    f.tick()
    assert f.transport.active.status == "failed"
    assert p.current_location == "input_queue"


def test_simulated_default_and_invalid_mode(monkeypatch):
    monkeypatch.delenv("TRANSPORT_MODE", raising=False)
    f = FactorySupervisor(enable_database=False, vision_source="synthetic")
    p = f.create_product("red_block")
    f.start()
    f.run_until_idle()
    assert f.transport is None and p.status == ProductStatus.COMPLETED
    with pytest.raises(ValueError, match="TRANSPORT_MODE"):
        FactorySupervisor(enable_database=False, transport_mode="typo")


def test_faulted_drill_reroutes_only_after_robot_delivery():
    f = FactorySupervisor(
        enable_database=False, transport_mode="amr", vision_source="synthetic"
    )
    p = f.create_product("red_block")
    f.start()
    for _ in range(20):
        f.transport.heartbeat(True)
        f.tick()
        if f.transport.active:
            deliver(f)
        if p.current_location in {"station_a", "station_b"}:
            break
    origin = p.current_location
    f.inject_fault(origin, FaultType.OVERHEAT)
    f.transport.heartbeat(True)
    f.tick()
    task = f.transport.active
    assert task and task.destination != origin
    assert p.current_location == origin and p.status == ProductStatus.IN_TRANSIT
    assert f.rerouted_product_count == 1
    deliver(f)
    assert p.current_location == task.destination and p.status == ProductStatus.PROCESSING


def test_many_products_never_share_a_station():
    f = FactorySupervisor(
        enable_database=False, transport_mode="amr", vision_source="synthetic"
    )
    for kind in ["red_block", "blue_cylinder", "green_component"] * 3:
        f.create_product(kind)
    f.start()
    for _ in range(300):
        f.transport.heartbeat(True)
        f.tick()
        if f.transport.active:
            deliver(f)
        occupied = [
            p.current_location
            for p in f.tracker.all()
            if p.current_location in f.stations
            and p.status not in {ProductStatus.COMPLETED, ProductStatus.REJECTED}
        ]
        assert len(occupied) == len(set(occupied))
        if f.is_idle():
            break
    assert all(p.status == ProductStatus.COMPLETED for p in f.tracker.all())


class MockHandle:
    def __init__(self, accepted=True):
        self.accepted = accepted
        self.result = Future()
        self.cancel_count = 0

    def get_result_async(self):
        return self.result

    def cancel_goal_async(self):
        self.cancel_count += 1
        return Future()


class MockClient:
    def __init__(self, ready=True, accepted=True):
        self.ready, self.accepted = ready, accepted
        self.handles = []
        self.goals = []

    def server_is_ready(self):
        return self.ready

    def send_goal_async(self, goal):
        self.goals.append(goal)
        handle = MockHandle(self.accepted)
        self.handles.append(handle)
        response = Future()
        response.set_result(handle)
        return response


def test_nav2_success_requires_two_action_successes():
    client, events = MockClient(), []
    runner = NavigationRunner(STATIONS, client, lambda p: p, events.append)
    runner.submit(request().to_dict())
    assert runner.task.status == "navigating" and len(client.goals) == 1
    client.handles[0].result.set_result(SimpleNamespace(status=4))
    assert runner.task.status == "navigating" and runner.task.phase == "delivery"
    assert client.goals[1] == STATIONS["vision"]
    client.handles[1].result.set_result(SimpleNamespace(status=4))
    assert runner.task.status == "delivered"
    assert [e["status"] for e in events] == [
        "accepted",
        "navigating",
        "navigating",
        "delivered",
    ]
    json.dumps(events)


def test_pickup_phase_update_records_elapsed_time():
    task = request()
    for status in ("accepted", "navigating"):
        task.update({**task.to_dict(), "status": status})
    task.update({**task.to_dict(), "phase": "delivery", "navigation_time_s": 12.5})
    assert task.phase == "delivery" and task.navigation_time_s == 12.5


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "invalid"])
def test_invalid_transport_timeout(monkeypatch, value):
    monkeypatch.setenv("AMR_TASK_TIMEOUT_S", value)
    with pytest.raises(ValueError):
        task_timeout_s()


def test_navigation_watchdog_uses_configured_budget(monkeypatch):
    monkeypatch.setenv("AMR_TASK_TIMEOUT_S", "12")
    now = [0.0]
    client = MockClient()
    runner = NavigationRunner(STATIONS, client, lambda p: p, lambda p: None, lambda: now[0])
    runner.submit(request().to_dict())
    now[0] = 11.0
    runner.watchdog()
    assert client.handles[0].cancel_count == 0
    now[0] = 13.0
    runner.watchdog()
    assert client.handles[0].cancel_count == 1
    assert runner.task.status != "delivered"


@pytest.mark.parametrize("ready,accepted", [(False, True), (True, False)])
def test_nav2_unavailable_or_rejects(ready, accepted):
    runner = NavigationRunner(
        STATIONS, MockClient(ready, accepted), lambda p: p, lambda p: None
    )
    runner.submit(request().to_dict())
    assert runner.task.status == "failed"


@pytest.mark.parametrize("result,cancelled", [(6, False), (5, False), (4, True)])
def test_nav2_abort_cancel_and_success_race(result, cancelled):
    client = MockClient()
    runner = NavigationRunner(STATIONS, client, lambda p: p, lambda p: None)
    runner.submit(request().to_dict())
    if cancelled:
        runner.cancel()
        assert client.handles[0].cancel_count == 1
    client.handles[0].result.set_result(SimpleNamespace(status=result))
    assert runner.task.status == ("failed" if result == 6 else "cancelled")
    assert len(client.goals) == 1
