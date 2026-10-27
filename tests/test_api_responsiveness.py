"""Slow optional operations must not block production controls on the API loop."""

import asyncio
import importlib.util
import sys
import threading
from pathlib import Path

import pytest

import reconfactory


@pytest.mark.parametrize("operation", ["stop", "reset", "complete"])
def test_ml_inference_keeps_authorization_responsive_and_discards_old_run(
    monkeypatch, operation
):
    from maintenance.ml import rule_prediction

    factory = reconfactory.FactorySupervisor(
        enable_database=False, transport_mode="amr", maintenance_mode="rules"
    )
    factory.start()
    monkeypatch.setattr(reconfactory, "FactorySupervisor", lambda **_: factory)
    spec = importlib.util.spec_from_file_location(
        "test_ml_api", Path(__file__).resolve().parents[1] / "app" / "main.py"
    )
    backend = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, backend)
    spec.loader.exec_module(backend)
    entered, release = threading.Event(), threading.Event()

    def slow_prediction(histories):
        entered.set()
        assert release.wait(3)
        return [rule_prediction(history) for history in histories]

    monkeypatch.setattr(factory.health_monitor, "estimator", object())
    monkeypatch.setattr(factory.health_monitor, "predict_histories", slow_prediction)

    async def scenario():
        pending = asyncio.create_task(backend._tick_supervisor())
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            assert not pending.done()
            assert (await backend.transport_state())["running"] is True
            if operation == "stop":
                await backend.stop()
                assert (await backend.transport_state())["running"] is False
            elif operation == "reset":
                await backend.reset()
                await backend.start()
            assert factory.tick_count == 0
        finally:
            release.set()
            await pending
        assert factory.tick_count == (1 if operation == "complete" else 0)

    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["integrations", "recovery_experiment"])
def test_start_responds_while_optional_operation_is_waiting(monkeypatch, operation):
    factory = reconfactory.FactorySupervisor(enable_database=False)
    monkeypatch.setattr(reconfactory, "FactorySupervisor", lambda **_: factory)
    spec = importlib.util.spec_from_file_location(
        "test_api_backend", Path(__file__).resolve().parents[1] / "app" / "main.py"
    )
    backend = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, backend)
    spec.loader.exec_module(backend)
    entered = threading.Event()
    release = threading.Event()

    def slow_work(**kwargs):
        entered.set()
        release.wait(3)
        return {"ok": True}

    worker_name = (
        "check_integrations" if operation == "integrations" else "run_recovery_comparison"
    )
    monkeypatch.setattr(backend, worker_name, slow_work)

    async def scenario():
        pending = asyncio.create_task(getattr(backend, operation)())
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            assert not pending.done(), "Optional operation blocked the API loop"
            result = await backend.start()
            assert result["running"] is True
            assert not pending.done()
            assert (await backend.stop())["running"] is False
        finally:
            release.set()
            await pending

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["amr", "simulated"])
def test_safety_api_is_observation_only_and_optional(monkeypatch, mode):
    from fastapi import HTTPException

    from reconfactory.amr_safety import MotionSafety

    factory = reconfactory.FactorySupervisor(
        transport_mode=mode, enable_database=False, maintenance_mode="rules"
    )
    monkeypatch.setattr(reconfactory, "FactorySupervisor", lambda **_: factory)
    spec = importlib.util.spec_from_file_location(
        "test_safety_api", Path(__file__).resolve().parents[1] / "app" / "main.py"
    )
    backend = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, backend)
    spec.loader.exec_module(backend)
    payload = backend.SafetyObservation(state=MotionSafety().snapshot(), events=[])
    if mode == "simulated":
        with pytest.raises(HTTPException) as error:
            asyncio.run(backend.transport_safety(payload))
        assert error.value.status_code == 409
        return
    assert asyncio.run(backend.transport_safety(payload)) == {"ok": True}
    assert factory.snapshot()["transport"]["safety"]["safety_state"] == "DISARMED"
    assert not factory.running and factory.transport.active is None
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            backend.transport_safety(backend.SafetyObservation(state={"safety_state": "bad"}))
        )
    assert error.value.status_code == 400


@pytest.mark.parametrize("mode", ["amr", "simulated"])
def test_actuator_api_remains_observation_only(monkeypatch, mode):
    from fastapi import HTTPException

    factory = reconfactory.FactorySupervisor(
        transport_mode=mode, enable_database=False, maintenance_mode="rules"
    )
    monkeypatch.setattr(reconfactory, "FactorySupervisor", lambda **_: factory)
    spec = importlib.util.spec_from_file_location(
        "test_actuator_api", Path(__file__).resolve().parents[1] / "app" / "main.py"
    )
    backend = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, backend)
    spec.loader.exec_module(backend)
    payload = backend.SafetyObservation(
        state={"state": "FAULT_LATCHED", "instance_id": "test", "sample_sequence": 1}
    )
    if mode == "simulated":
        with pytest.raises(HTTPException) as error:
            asyncio.run(backend.transport_actuator(payload))
        assert error.value.status_code == 409
    else:
        assert asyncio.run(backend.transport_actuator(payload)) == {"ok": True}
        assert not factory.running and factory.transport.active is None
        assert factory.transport.actuator_snapshot()["state"] == "FAULT_LATCHED"
        with pytest.raises(HTTPException) as error:
            asyncio.run(
                backend.transport_actuator(backend.SafetyObservation(state={"state": "bad"}))
            )
        assert error.value.status_code == 400
