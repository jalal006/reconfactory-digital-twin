from reconfactory.config import DEFAULT_MACHINE_CONFIGS, DEFAULT_RECIPES
from reconfactory.models import FaultType
from reconfactory.scheduler import ProductionScheduler
from reconfactory.stations import StationController
from reconfactory.tracker import ProductTracker


def _processing_stations():
    stations = {
        key: StationController(DEFAULT_MACHINE_CONFIGS[key])
        for key in ["station_a", "station_b"]
    }
    for station in stations.values():
        station.start()
    return stations


def test_scheduler_chooses_fastest_compatible_drill_station():
    stations = _processing_stations()
    tracker = ProductTracker(DEFAULT_RECIPES)
    product = tracker.create_product("red_block")
    scheduler = ProductionScheduler(stations)

    selected = scheduler.select_station(product, "drill")

    assert selected is not None
    assert selected.machine_id == "station_a"


def test_scheduler_selects_station_b_for_polishing():
    stations = _processing_stations()
    tracker = ProductTracker(DEFAULT_RECIPES)
    product = tracker.create_product("blue_cylinder")
    scheduler = ProductionScheduler(stations)

    selected = scheduler.select_station(product, "polish")

    assert selected is not None
    assert selected.machine_id == "station_b"


def test_scheduler_avoids_faulted_station():
    stations = _processing_stations()
    stations["station_a"].inject_fault(FaultType.OVERHEAT)
    tracker = ProductTracker(DEFAULT_RECIPES)
    product = tracker.create_product("red_block")
    scheduler = ProductionScheduler(stations)

    selected = scheduler.select_station(product, "drill")

    assert selected is not None
    assert selected.machine_id == "station_b"
