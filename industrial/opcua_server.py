"""Optional OPC UA server.

Install the project requirements before running:

    python -m pip install -r requirements.txt
"""

from __future__ import annotations

import asyncio
import json
import urllib.request


class BackendClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000") -> None:
        self.base_url = base_url.rstrip("/")

    def status(self) -> dict:
        with urllib.request.urlopen(f"{self.base_url}/api/status", timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))


async def main() -> None:
    try:
        from asyncua import Server, ua
    except ImportError as exc:
        raise SystemExit(
            "Install dependencies: python -m pip install -r requirements.txt"
        ) from exc

    server = Server()
    await server.init()
    server.set_endpoint("opc.tcp://0.0.0.0:4840/reconfactory/server/")
    idx = await server.register_namespace("urn:reconfactory:digital_twin")
    objects = server.nodes.objects
    factory = await objects.add_object(idx, "Factory")
    running = await factory.add_variable(idx, "Running", False)
    tick = await factory.add_variable(idx, "Tick", 0)
    completed = await factory.add_variable(idx, "CompletedProducts", 0)
    faults = await factory.add_variable(idx, "FaultCount", 0)
    rerouted = await factory.add_variable(idx, "ReroutedProducts", 0)
    for node in [running, tick, completed, faults, rerouted]:
        await node.set_writable(False)

    client = BackendClient()
    async with server:
        while True:
            snapshot = client.status()
            stats = snapshot["stats"]
            await running.write_value(snapshot["running"], ua.VariantType.Boolean)
            await tick.write_value(snapshot["tick"], ua.VariantType.Int64)
            await completed.write_value(stats["completed_products"], ua.VariantType.Int64)
            await faults.write_value(stats["fault_count"], ua.VariantType.Int64)
            await rerouted.write_value(stats["rerouted_products"], ua.VariantType.Int64)
            await asyncio.sleep(0.5)


if __name__ == "__main__":
    asyncio.run(main())
