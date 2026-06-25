import pytest

from reconfactory.config import DEFAULT_RECIPES
from reconfactory.models import ProductStatus
from reconfactory.tracker import ProductTracker


def test_tracker_creates_unique_products_and_tracks_route():
    tracker = ProductTracker(DEFAULT_RECIPES)

    first = tracker.create_product("red_block")
    second = tracker.create_product("blue_cylinder")

    assert first.product_id == "P-00001"
    assert second.product_id == "P-00002"

    tracker.move(first.product_id, "vision")
    tracker.update_status(first.product_id, ProductStatus.PROCESSING)
    tracker.complete_process(first.product_id, "visual_inspection")

    updated = tracker.get(first.product_id)
    assert updated.current_location == "vision"
    assert updated.completed_processes == ["visual_inspection"]
    assert updated.next_process() == "drill"
    assert "vision" in updated.route


def test_tracker_prevents_moving_finalized_product():
    tracker = ProductTracker(DEFAULT_RECIPES)
    product = tracker.create_product("red_block")
    tracker.mark_quality(product.product_id, accepted=True)

    with pytest.raises(ValueError):
        tracker.move(product.product_id, "station_a")
