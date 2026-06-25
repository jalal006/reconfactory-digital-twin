import pytest

from reconfactory import FactorySupervisor
from reconfactory.models import FaultType, ProductStatus


def test_normal_production_completes_three_product_types():
    factory = FactorySupervisor(enable_database=False)
    factory.start()
    factory.create_product("red_block")
    factory.create_product("blue_cylinder")
    factory.create_product("green_component")

    snapshot = factory.run_until_idle(max_ticks=120)

    assert snapshot["stats"]["total_products"] == 3
    assert snapshot["stats"]["completed_products"] == 3
    assert snapshot["stats"]["rejected_products"] == 0


def test_defective_product_is_rejected_by_vision():
    factory = FactorySupervisor(enable_database=False)
    factory.start()
    product = factory.create_product("red_block", defect_flags=["wrong_colour"])

    snapshot = factory.run_until_idle(max_ticks=30)

    updated = factory.tracker.get(product.product_id)
    assert snapshot["stats"]["rejected_products"] == 1
    assert updated.current_location == "reject_output"
    assert updated.defect_reason == "Colour does not match recipe"


def test_live_vision_station_uses_opencv_color_and_shape_features():
    factory = FactorySupervisor(enable_database=False)
    factory.start()
    product = factory.create_product("red_block")

    factory.run_until_idle(max_ticks=30)

    vision_event = next(
        event
        for event in factory.snapshot()["events"]
        if event["event_type"] == "vision_passed"
        and event["data"].get("product_id") == product.product_id
    )
    inspection = vision_event["data"]["inspection"]
    assert inspection["method"] == "opencv"
    assert inspection["features"]["dominant_color"] == "red"
    assert inspection["features"]["detected_shape"] == "block"


def test_pause_freezes_current_operation_and_resume_continues():
    factory = FactorySupervisor(enable_database=False)
    factory.start()
    product = factory.create_product("green_component")
    factory.tick(1)

    assert factory.tracker.get(product.product_id).assigned_station == "vision"
    remaining_before_pause = factory.stations["vision"].remaining_ticks
    tick_before_pause = factory.tick_count

    factory.stop()
    factory.tick(5)

    assert factory.tick_count == tick_before_pause
    assert factory.stations["vision"].remaining_ticks == remaining_before_pause
    assert factory.tracker.get(product.product_id).assigned_station == "vision"

    factory.start()
    snapshot = factory.run_until_idle(max_ticks=120)

    updated = factory.tracker.get(product.product_id)
    assert updated.status == ProductStatus.COMPLETED
    assert updated.current_location == "accepted_output"
    assert snapshot["stats"]["completed_products"] == 1


def test_snapshot_includes_sanitized_gazebo_visual_poses():
    factory = FactorySupervisor(enable_database=False)
    product = factory.create_product("red_block")

    result = factory.update_gazebo_visuals(
        {
            "updated_at": 123.0,
            "products": {
                product.product_id: {"x": 1, "y": 2, "z": 3, "yaw": 0.5},
                "P-99999": {"x": 9, "y": 9, "z": 9, "yaw": 9},
            },
        }
    )
    visuals = factory.snapshot()["gazebo_visuals"]

    assert result == {"accepted": 1}
    assert visuals["source"] == "gazebo"
    assert visuals["updated_at"] == 123.0
    assert visuals["products"] == {
        product.product_id: {"x": 1.0, "y": 2.0, "z": 3.0, "yaw": 0.5}
    }


@pytest.mark.parametrize(
    ("product_type", "faulted_machine", "fault_type", "expected_status", "expected_location"),
    [
        (
            "red_block",
            "station_a",
            FaultType.OVERHEAT,
            ProductStatus.COMPLETED,
            "accepted_output",
        ),
        ("red_block", "station_b", FaultType.JAM, ProductStatus.COMPLETED, "accepted_output"),
        (
            "blue_cylinder",
            "station_a",
            FaultType.OVERHEAT,
            ProductStatus.COMPLETED,
            "accepted_output",
        ),
        (
            "blue_cylinder",
            "station_b",
            FaultType.JAM,
            ProductStatus.PAUSED,
            "processing_buffer",
        ),
        (
            "green_component",
            "station_a",
            FaultType.OVERHEAT,
            ProductStatus.PAUSED,
            "processing_buffer",
        ),
        (
            "green_component",
            "station_b",
            FaultType.JAM,
            ProductStatus.COMPLETED,
            "accepted_output",
        ),
    ],
)
def test_product_type_outcomes_when_processing_station_is_unavailable(
    product_type,
    faulted_machine,
    fault_type,
    expected_status,
    expected_location,
):
    factory = FactorySupervisor(enable_database=False)
    factory.start()
    factory.inject_fault(faulted_machine, fault_type)
    product = factory.create_product(product_type)

    snapshot = factory.run_until_idle(max_ticks=120)
    updated = factory.tracker.get(product.product_id)

    assert updated.status == expected_status
    assert updated.current_location == expected_location
    if expected_status == ProductStatus.COMPLETED:
        assert snapshot["stats"]["completed_products"] == 1
        assert snapshot["stats"]["paused_products"] == 0
    else:
        assert snapshot["stats"]["completed_products"] == 0
        assert snapshot["stats"]["paused_products"] == 1
        assert "No healthy" in updated.recovery_notes[-1]


@pytest.mark.parametrize("product_type", ["red_block", "blue_cylinder", "green_component"])
def test_vision_failure_during_inspection_pauses_each_product_type(product_type):
    factory = FactorySupervisor(enable_database=False)
    factory.start()
    product = factory.create_product(product_type)
    factory.tick(1)

    factory.inject_fault("vision", FaultType.CAMERA_FAILURE)

    updated = factory.tracker.get(product.product_id)
    assert updated.status == ProductStatus.PAUSED
    assert updated.current_location == "recovery_buffer"
    assert "Vision Inspection failed" in updated.recovery_notes[-1]


@pytest.mark.parametrize("product_type", ["red_block", "blue_cylinder", "green_component"])
def test_quality_failure_during_check_pauses_each_product_type(product_type):
    factory = FactorySupervisor(enable_database=False)
    factory.start()
    product = factory.create_product(product_type)

    for _ in range(20):
        factory.tick(1)
        if factory.tracker.get(product.product_id).assigned_station == "quality":
            break
    else:
        pytest.fail(f"{product_type} did not reach quality control")

    factory.inject_fault("quality", FaultType.COMMUNICATION_LOSS)

    updated = factory.tracker.get(product.product_id)
    assert updated.status == ProductStatus.PAUSED
    assert updated.current_location == "recovery_buffer"
    assert "Quality Control failed" in updated.recovery_notes[-1]
