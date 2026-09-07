"""Slow optional operations must not block production controls on the API loop."""

import asyncio
import importlib.util
import sys
import threading
from pathlib import Path

import pytest

import reconfactory


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
