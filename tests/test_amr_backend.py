import sys
import threading
from pathlib import Path
from urllib.error import HTTPError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ros2_ws/src/reconfactory_amr"))
from reconfactory_amr.backend import BackendWorker  # noqa: E402


def test_backend_snapshot_only_refreshes_after_successful_response():
    now = [10.0]
    io = BackendWorker(
        "unused", request=lambda *args: {"running": True}, clock=lambda: now[0], start=False
    )
    io.cycle()
    assert io.snapshot == ({"running": True}, 10.0)
    now[0] = 11.0
    assert io.snapshot[1] == 10.0


def test_backend_status_retry_preserves_order_and_payload_snapshot():
    sent = []

    def request(path, payload=None):
        if path.endswith("/status"):
            sent.append(payload["id"])
            if len(sent) == 1:
                raise TimeoutError("unavailable")
        return {"running": True}

    io = BackendWorker("unused", request=request, clock=lambda: 10, start=False)
    payload = {"id": 1}
    assert io.enqueue(payload)
    payload["id"] = 99
    io.enqueue({"id": 2})
    io.cycle()
    assert io.snapshot == ({}, 0.0)
    io.cycle()
    io.cycle()
    assert sent == [1, 1, 2]


@pytest.mark.parametrize("code,retained", [(409, False), (500, True)])
def test_backend_rejected_stale_status_is_not_replayed_forever(code, retained):
    def request(path, payload=None):
        if path.endswith("/status"):
            raise HTTPError(path, code, "failure", None, None)
        return {}

    io = BackendWorker("unused", request=request, start=False)
    io.enqueue({"task_id": "T-1"})
    io.cycle()
    assert (io.pending is not None) == retained


def test_heartbeat_is_latest_only_copied_and_expires():
    now, sent = [10.0], []
    io = BackendWorker(
        "unused",
        request=lambda path, payload=None: sent.append((path, payload)) or {},
        clock=lambda: now[0],
        start=False,
    )
    payload = {"ready": True}
    io.set_heartbeat(payload)
    payload["ready"] = False
    io.cycle()
    io.cycle()
    heartbeats = [p for path, p in sent if path.endswith("/heartbeat")]
    assert heartbeats == [{"ready": True}]
    io.set_heartbeat({"ready": False})
    now[0] += 0.6
    io.cycle()
    assert len([p for path, p in sent if path.endswith("/heartbeat")]) == 1


def test_backend_queue_overflow_is_latched_unavailable():
    io = BackendWorker("unused", request=lambda *args: {}, start=False)
    for i in range(512):
        assert io.enqueue({"id": i})
    assert not io.enqueue({"id": 513})
    io.cycle()
    assert io.snapshot == ({}, 0.0)
    assert io.overflow


def test_blocked_http_worker_does_not_block_ros_side_access():
    entered, release = threading.Event(), threading.Event()

    def request(*args):
        entered.set()
        assert release.wait(2)
        return {}

    io = BackendWorker("unused", request=request)
    try:
        assert entered.wait(1)
        assert io.enqueue({"id": 1})
        io.set_heartbeat({"ready": False})
        assert io.snapshot == ({}, 0.0)
    finally:
        release.set()
        io.close()
    assert not io.thread.is_alive()


def test_invalid_backend_observation_fails_closed():
    io = BackendWorker("unused", request=lambda *args: [], start=False)
    io.cycle()
    assert io.snapshot == ({}, 0.0)
    assert "Invalid backend" in io.error
