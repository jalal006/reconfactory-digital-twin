"""Bounded HTTP I/O for the manager; never runs on the ROS executor thread."""

from __future__ import annotations

import copy
import json
import queue
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class BackendWorker:
    def __init__(self, url, *, request=None, clock=time.monotonic, start=True):
        self.url = url.rstrip("/")
        self.request = request or self._request
        self.clock = clock
        self._snapshot = ({}, 0.0)
        self.error = "Waiting for backend observation"
        self.statuses = queue.Queue(maxsize=512)
        self.pending = None
        self.heartbeat = None
        self.sent_heartbeat = None
        self.overflow = False
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        if start:
            self.thread.start()

    @property
    def snapshot(self):
        return ({}, 0.0) if self.overflow else self._snapshot

    def _request(self, path, payload=None):
        req = Request(
            self.url + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=0.5) as response:
            return json.load(response)

    def enqueue(self, payload):
        try:
            self.statuses.put_nowait(copy.deepcopy(payload))
            return True
        except queue.Full:
            self.overflow = True
            self._snapshot = ({}, 0.0)
            self.error = "Backend status queue overflow; reconcile before restart"
            return False

    def set_heartbeat(self, payload):
        self.heartbeat = (copy.deepcopy(payload), self.clock())

    def cycle(self):
        if self.overflow:
            return
        try:
            state = self.request("/api/transport")
            if not isinstance(state, dict):
                raise ValueError("Invalid backend transport observation")
            self._snapshot = (state, self.clock())
            if self.pending is None:
                try:
                    self.pending = self.statuses.get_nowait()
                except queue.Empty:
                    pass
            if self.pending is not None:
                try:
                    self.request("/api/transport/status", self.pending)
                except HTTPError as exc:
                    if exc.code != 409:
                        raise
                self.pending = None
            heartbeat = self.heartbeat
            if heartbeat is not None and heartbeat is not self.sent_heartbeat:
                payload, created_at = heartbeat
                if self.clock() - created_at < 0.5:
                    self.request("/api/transport/heartbeat", payload)
                self.sent_heartbeat = heartbeat
            self.error = ""
        except Exception as exc:
            self._snapshot = ({}, 0.0)
            self.error = str(exc)

    def _run(self):
        while not self.stop.wait(0.1):
            self.cycle()

    def close(self):
        self.stop.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)
