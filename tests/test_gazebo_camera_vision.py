from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

from reconfactory import FactorySupervisor
from reconfactory.config import DEFAULT_RECIPES
from reconfactory.models import ProductStatus
from vision.opencv_inspector import OpenCVInspector

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "ros2_ws" / "src" / "reconfactory_ros"
MODULE_ROOT = PACKAGE_ROOT / "reconfactory_ros"


def load_vision_node_module():
    package_parent = str(PACKAGE_ROOT)
    if package_parent not in sys.path:
        sys.path.insert(0, package_parent)
    path = MODULE_ROOT / "vision_inspector_node.py"
    spec = importlib.util.spec_from_file_location(
        "reconfactory_ros.vision_inspector_node", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("product_type", list(DEFAULT_RECIPES))
@pytest.mark.parametrize("wrong_color", [False, True])
def test_camera_color_only_decision_reaches_supervisor(product_type, wrong_color):
    inspector = OpenCVInspector()
    recipe = DEFAULT_RECIPES[product_type]
    frame = inspector.create_synthetic_image(recipe, wrong_shape=True, wrong_color=wrong_color)
    inspection = inspector.inspect_image(frame, recipe, enforce_area=False, enforce_shape=False)
    assert inspection[0].passed is (not wrong_color)
    aggregate = inspector.aggregate_results(
        [inspection] * 5, recipe, enforce_area=False, enforce_shape=False
    )
    factory = FactorySupervisor(enable_database=False, vision_source="gazebo")
    factory.start()
    product = factory.create_product(product_type)
    factory.tick(2)
    factory.accept_vision_result(aggregate.to_payload(product_id=product.product_id))
    assert factory.last_inspection_result["passed"] is (not wrong_color)
    assert (product.status == ProductStatus.REJECTED) is wrong_color


def test_arbitrary_opencv_frame_can_be_inspected():
    inspector = OpenCVInspector()
    recipe = DEFAULT_RECIPES["green_component"]
    frame = inspector.create_synthetic_image(recipe)

    result, features = inspector.inspect_image(frame, recipe)

    assert result.passed
    assert result.method == "opencv"
    assert features.dominant_color == "green"
    assert features.detected_shape == "component"


def test_empty_camera_frame_is_handled_safely():
    inspector = OpenCVInspector()
    recipe = DEFAULT_RECIPES["red_block"]
    frame = np.zeros((240, 320, 3), dtype=np.uint8)

    result, features = inspector.inspect_image(frame, recipe)

    assert not result.passed
    assert result.confidence == 0.0
    assert result.defect_reason == "No product contour detected"
    assert features.area == 0.0
    assert features.missing_material


def test_multiframe_aggregation_majority_votes_and_serializes_payload():
    inspector = OpenCVInspector()
    recipe = DEFAULT_RECIPES["red_block"]
    good = inspector.inspect_image(inspector.create_synthetic_image(recipe), recipe)
    missing = inspector.inspect_image(
        inspector.create_synthetic_image(recipe, missing_section=True), recipe
    )

    aggregated = inspector.aggregate_results([good, good, missing], recipe)
    payload = aggregated.to_payload(product_id="P-00001")

    assert aggregated.result.passed
    assert aggregated.frame_count == 3
    assert payload["product_id"] == "P-00001"
    assert payload["source"] == "gazebo_camera"
    assert payload["detected_color"] == "red"
    assert payload["detected_shape"] == "block"
    assert payload["accepted"] is True
    assert payload["features"]["detected_color"] == "red"


def test_gazebo_camera_mode_does_not_reject_uncalibrated_camera_area():
    inspector = OpenCVInspector()
    recipe = DEFAULT_RECIPES["red_block"]
    frame = np.full((480, 640, 3), 245, dtype=np.uint8)
    frame[120:360, 200:440] = (68, 68, 239)

    inspection = inspector.inspect_image(frame, recipe, enforce_area=False)
    aggregated = inspector.aggregate_results([inspection] * 5, recipe, enforce_area=False)

    assert aggregated.result.passed
    assert aggregated.features.dominant_color == "red"
    assert aggregated.features.detected_shape == "block"
    assert aggregated.features.missing_material is False


def test_gazebo_camera_mode_prefers_expected_colour_over_scene_distractions():
    inspector = OpenCVInspector()
    recipe = DEFAULT_RECIPES["red_block"]
    frame = np.full((480, 640, 3), 245, dtype=np.uint8)
    frame[40:440, 40:600] = (80, 190, 40)
    frame[190:290, 270:370] = (68, 68, 239)

    result, features = inspector.inspect_image(frame, recipe, enforce_area=False)

    assert result.passed
    assert features.dominant_color == "red"
    assert features.detected_shape == "block"


def test_ros_vision_node_ignores_products_until_supervisor_requests_camera_result():
    module = load_vision_node_module()
    snapshot = {
        "pending_vision_product_id": None,
        "products": [
            {
                "product_id": "P-00001",
                "product_type": "red_block",
                "status": "processing",
                "assigned_station": "vision",
                "current_location": "vision",
            }
        ],
        "recipes": {"red_block": DEFAULT_RECIPES["red_block"].to_dict()},
    }

    assert module.active_vision_product(snapshot) is None


def test_ros_vision_node_waits_until_gazebo_reports_product_at_vision():
    module = load_vision_node_module()
    snapshot = {
        "pending_vision_product_id": "P-00001",
        "gazebo_visuals": {"product_locations": {"P-00001": "input_queue"}},
        "products": [
            {
                "product_id": "P-00001",
                "product_type": "red_block",
                "status": "processing",
                "assigned_station": "vision",
                "current_location": "vision",
            }
        ],
        "recipes": {"red_block": DEFAULT_RECIPES["red_block"].to_dict()},
    }

    assert module.active_vision_product(snapshot) is None


def test_gazebo_vision_mode_waits_for_external_result_then_routes_product():
    factory = FactorySupervisor(enable_database=False, vision_source="gazebo")
    factory.start()
    product = factory.create_product("red_block")

    factory.tick(2)
    waiting = factory.tracker.get(product.product_id)

    assert factory.pending_vision_product_id == product.product_id
    assert waiting.status == ProductStatus.PROCESSING
    assert waiting.assigned_station == "vision"
    assert waiting.completed_processes == []

    snapshot = factory.accept_vision_result(
        {
            "product_id": product.product_id,
            "source": "gazebo_camera",
            "accepted": True,
            "detected_color": "red",
            "detected_shape": "block",
            "area_ratio": 1.0,
            "missing_material": False,
            "confidence": 0.95,
            "frame_count": 5,
        }
    )
    updated = factory.tracker.get(product.product_id)

    assert factory.pending_vision_product_id is None
    assert "visual_inspection" in updated.completed_processes
    assert updated.assigned_station in {"station_a", None}
    assert snapshot["last_inspection_result"]["method"] == "gazebo_camera"


def test_gazebo_vision_mode_rejects_external_defect_result():
    factory = FactorySupervisor(enable_database=False, vision_source="gazebo")
    factory.start()
    product = factory.create_product("red_block")
    factory.tick(2)

    factory.accept_vision_result(
        {
            "product_id": product.product_id,
            "source": "gazebo_camera",
            "accepted": False,
            "detected_color": "blue",
            "detected_shape": "block",
            "area_ratio": 1.0,
            "confidence": 0.6,
            "defect_reason": "incorrect_colour",
            "frame_count": 5,
        }
    )
    updated = factory.tracker.get(product.product_id)

    assert updated.status == ProductStatus.REJECTED
    assert updated.current_location == "reject_output"
    assert updated.defect_reason == "Colour does not match recipe"


def test_gazebo_vision_mode_falls_back_to_synthetic_on_timeout():
    factory = FactorySupervisor(
        enable_database=False, vision_source="gazebo", vision_timeout_ticks=2
    )
    factory.start()
    product = factory.create_product("red_block")
    factory.tick(2)

    factory.tick(2)
    updated = factory.tracker.get(product.product_id)
    event_types = [event["event_type"] for event in factory.snapshot()["events"]]

    assert factory.pending_vision_product_id is None
    assert "visual_inspection" in updated.completed_processes
    assert "vision_camera_timeout" in event_types


def test_ros_vision_node_finds_pending_product_and_builds_payload():
    module = load_vision_node_module()
    snapshot = {
        "pending_vision_product_id": "P-00001",
        "gazebo_visuals": {"product_locations": {"P-00001": "vision"}},
        "products": [
            {
                "product_id": "P-00001",
                "product_type": "red_block",
                "status": "processing",
                "assigned_station": "vision",
                "current_location": "vision",
            }
        ],
        "recipes": {"red_block": DEFAULT_RECIPES["red_block"].to_dict()},
    }

    active = module.active_vision_product(snapshot)
    recipe = module.recipe_from_snapshot(snapshot, active.product_type)

    assert active.product_id == "P-00001"
    assert recipe.shape == "block"


def test_ros_vision_node_recipe_lookup_requires_backend_recipe():
    module = load_vision_node_module()

    with pytest.raises(KeyError):
        module.recipe_from_snapshot({"recipes": {}}, "red_block")


def test_frame_window_clears_delivery_state_for_next_product():
    module = load_vision_node_module()
    window = module.FrameWindow()
    window.reset("P-00001")
    window.final_payload = {"product_id": "P-00001", "accepted": True}
    window.submitted = True
    window.retry_at = 123.0
    window.reset("P-00002")
    assert window.product_id == "P-00002"
    assert window.final_payload is None
    assert not window.submitted
    assert window.retry_at == 0.0


def test_camera_result_is_authoritative_and_metadata_is_persisted(tmp_path, monkeypatch):
    factory = FactorySupervisor(db_path=tmp_path / "factory.db", vision_source="gazebo")
    factory.start()
    product = factory.create_product("red_block")
    factory.tick(2)

    def unexpected_synthetic_inspection(_):
        pytest.fail("Camera result must not trigger a second synthetic inspection")

    monkeypatch.setattr(factory.vision_inspector, "inspect", unexpected_synthetic_inspection)
    payload = {
        "product_id": product.product_id,
        "source": "gazebo_camera",
        "accepted": True,
        "confidence": 0.9,
        "detected_color": "red",
        "area_ratio": 2.4,
        "inspection_latency_ms": 350.0,
        "frame_count": 5,
    }
    factory.accept_vision_result(json.loads(json.dumps(payload)))
    factory.accept_vision_result(payload)
    with sqlite3.connect(factory.logger.db_path) as connection:
        rows = connection.execute(
            "SELECT data_json FROM events WHERE event_type = 'vision_passed'"
        ).fetchall()
    assert len(rows) == 1
    result = json.loads(rows[0][0])["inspection"]
    assert result["method"] == "gazebo_camera"
    assert result["confidence"] == 0.9
    for key in ("source", "area_ratio", "inspection_latency_ms", "frame_count"):
        assert result["features"][key] == payload[key]


def test_camera_timeout_event_preserves_fallback_method():
    factory = FactorySupervisor(
        enable_database=False, vision_source="gazebo", vision_timeout_ticks=1
    )
    factory.start()
    factory.create_product("red_block")
    factory.tick(3)
    passed = next(e for e in factory.snapshot()["events"] if e["event_type"] == "vision_passed")
    assert passed["data"]["inspection"]["method"].endswith("_after_camera_timeout")
    assert passed["data"]["inspection"] == factory.last_inspection_result


def test_invalid_vision_source_falls_back_to_synthetic(monkeypatch):
    monkeypatch.setenv("VISION_SOURCE", "unavailable-mode")
    factory = FactorySupervisor(enable_database=False)
    assert factory.vision_source == "synthetic"


@pytest.mark.parametrize("product_type", list(DEFAULT_RECIPES))
@pytest.mark.parametrize(
    "defects",
    [
        [],
        ["wrong_shape"],
        ["missing_part"],
        ["quality_defect"],
        ["wrong_shape", "missing_part"],
    ],
)
def test_final_quality_catches_structural_defects_after_camera_color_pass(
    product_type, defects
):
    factory = FactorySupervisor(enable_database=False, vision_source="gazebo")
    factory.start()
    product = factory.create_product(product_type, defects)
    factory.tick(2)
    factory.accept_vision_result(
        {
            "product_id": product.product_id,
            "source": "gazebo_camera",
            "accepted": True,
            "confidence": 1.0,
            "frame_count": 5,
        }
    )
    snapshot = factory.run_until_idle(max_ticks=60)
    assert product.status == (ProductStatus.REJECTED if defects else ProductStatus.COMPLETED)
    assert "quality_check" in product.completed_processes
    assert product.route.count("quality") == 1
    assert product.route.count(product.current_location) == 1
    assert factory.last_inspection_result["method"] == "gazebo_camera"
    assert factory.last_inspection_result["passed"] is True
    events = [
        e
        for e in snapshot["events"]
        if e["event_type"] in {"product_completed", "product_rejected"}
    ]
    assert len(events) == 1
    assert events[0]["source"] == "quality"
    assert events[0]["data"]["defect_flags"] == defects
    if "wrong_shape" in defects:
        assert "Shape does not match recipe" in product.defect_reason
    if "missing_part" in defects:
        assert "Required part is missing" in product.defect_reason
