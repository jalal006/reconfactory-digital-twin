from reconfactory import FactorySupervisor
from reconfactory.models import FaultType, MachineState, ProductStatus


def _machine(snapshot, machine_id):
    return next(
        machine for machine in snapshot["machines"] if machine["machine_id"] == machine_id
    )


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

    factory.recover_machine("conveyor_main")
    assert factory.running
    assert factory.stations["conveyor_main"].state == MachineState.IDLE


def test_recovery_check_clears_fault_and_logs_result():
    factory = FactorySupervisor(enable_database=False)
    factory.start()

    faulted = factory.inject_fault("station_a", FaultType.OVERHEAT)
    assert _machine(faulted, "station_a")["state"] == "fault"
    assert _machine(faulted, "station_a")["active_fault"]

    recovered = factory.recover_machine("station_a")
    station = _machine(recovered, "station_a")
    event_types = [event["event_type"] for event in recovered["events"]]

    assert station["state"] == "idle"
    assert station["healthy"]
    assert station["active_fault"] is None
    assert "recovery_check_started" in event_types
    assert "machine_recovered" in event_types
    assert "recovery check passed" in recovered["last_decision"]


def test_recovery_resumes_product_paused_by_faulted_station():
    factory = FactorySupervisor(enable_database=False)
    factory.start()
    product = factory.create_product("green_component")

    factory.tick(2)
    assert factory.stations["station_a"].current_product_id == product.product_id

    factory.inject_fault("station_a", FaultType.OVERHEAT)
    paused = factory.tracker.get(product.product_id)
    assert paused.status == ProductStatus.PAUSED
    assert paused.current_location == "recovery_buffer"

    factory.recover_machine("station_a")
    resumed = factory.tracker.get(product.product_id)

    assert resumed.status == ProductStatus.PROCESSING
    assert resumed.assigned_station == "station_a"
    assert resumed.current_location == "station_a"


def test_recovery_does_not_restart_operator_paused_line():
    factory = FactorySupervisor(enable_database=False)
    factory.start()
    factory.stop()

    factory.inject_fault("conveyor_main", FaultType.JAM)
    assert not factory.running

    snapshot = factory.recover_machine("conveyor_main")

    assert not snapshot["running"]
    assert factory.stations["conveyor_main"].state == MachineState.IDLE
