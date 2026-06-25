"""Small HTTP client used by ROS 2 bridge nodes."""

from __future__ import annotations

import json
import urllib.request
from typing import Any


class ReConFactoryClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000") -> None:
        self.base_url = base_url.rstrip("/")

    def status(self) -> dict[str, Any]:
        with urllib.request.urlopen(f"{self.base_url}/api/status", timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))

    def post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload or {}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))
