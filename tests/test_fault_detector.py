from reconfactory.config import DEFAULT_FAULT_RULES, DEFAULT_MACHINE_CONFIGS
from reconfactory.faults import FaultDetector
from reconfactory.models import FaultType
from reconfactory.stations import StationController


def test_fault_detector_detects_overheat():
    station = StationController(DEFAULT_MACHINE_CONFIGS["station_a"])
    station.start()
    station.sensors.temperature_c = 90
    detector = FaultDetector(DEFAULT_FAULT_RULES)

    faults = detector.evaluate({"station_a": station})

    assert len(faults) == 1
    assert faults[0].fault_type == FaultType.OVERHEAT


def test_fault_detector_detects_camera_failure():
    station = StationController(DEFAULT_MACHINE_CONFIGS["vision"])
    station.start()
    station.sensors.camera_ok = False
    detector = FaultDetector(DEFAULT_FAULT_RULES)

    faults = detector.evaluate({"vision": station})

    assert len(faults) == 1
    assert faults[0].fault_type == FaultType.CAMERA_FAILURE


def test_fault_detector_ignores_already_faulted_station():
    station = StationController(DEFAULT_MACHINE_CONFIGS["station_a"])
    station.start()
    station.inject_fault(FaultType.OVERHEAT)
    detector = FaultDetector(DEFAULT_FAULT_RULES)

    faults = detector.evaluate({"station_a": station})

    assert faults == []
