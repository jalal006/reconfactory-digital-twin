from reconfactory import FactorySupervisor
from reconfactory.models import FaultType, MachineState, ProductStatus


def test_station_a_failure_reroutes_drill_product_to_station_b():
    factory = FactorySupervisor(enable_database=False)
    factory.start()
    product = factory.create_product("red_block")

    factory.tick(2)
    assert factory.stations["station_a"].current_product_id == product.product_id

    factory.inject_fault("station_a", FaultType.OVERHEAT)

    updated = factory.tracker.get(product.product_id)
    assert factory.stations["station_a"].state == MachineState.FAULT
    assert factory.stations["station_b"].current_product_id == product.product_id
    assert updated.assigned_station == "station_b"
    assert updated.status == ProductStatus.PROCESSING
    assert factory.snapshot()["stats"]["rerouted_products"] == 1


def test_station_a_failure_pauses_assembly_product_when_no_backup_exists():
    factory = FactorySupervisor(enable_database=False)
    factory.start()
    product = factory.create_product("green_component")

    factory.tick(2)
    assert factory.stations["station_a"].current_product_id == product.product_id

    factory.inject_fault("station_a", FaultType.OVERHEAT)

    updated = factory.tracker.get(product.product_id)
    assert updated.status == ProductStatus.PAUSED
    assert updated.assigned_station is None
    assert "No healthy processing station" in updated.recovery_notes[-1]


def test_conveyor_jam_stops_factory_until_recovery():
    factory = FactorySupervisor(enable_database=False)
    factory.start()

    factory.inject_fault("conveyor_main", FaultType.JAM)

    assert not factory.running
    assert factory.stations["conveyor_main"].state == MachineState.FAULT

    factory.start()
    assert factory.running
    factory.recover_machine("conveyor_main")
    assert factory.stations["conveyor_main"].state == MachineState.IDLE
