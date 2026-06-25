"""FastAPI backend for the ReConFactory dashboard."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from analytics.metrics import run_recovery_comparison
from integrations import check_integrations
from reconfactory import AUTO_TICK_SECONDS, FactorySupervisor
from reconfactory.models import FaultType

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"


class ProductCreateRequest(BaseModel):
    product_type: str
    defect_flags: list[str] = Field(default_factory=list)


class FaultInjectRequest(BaseModel):
    machine_id: str
    fault_type: FaultType
    reason: str | None = None


class RecoverRequest(BaseModel):
    machine_id: str


class TickRequest(BaseModel):
    steps: int = Field(default=1, ge=1, le=100)


class SpeedRequest(BaseModel):
    speed: float = Field(default=1.0, ge=0.25, le=4.0)


class GazeboVisualsRequest(BaseModel):
    products: dict[str, dict[str, float]] = Field(default_factory=dict)
    product_locations: dict[str, str] = Field(default_factory=dict)
    processing_locations: list[str] = Field(default_factory=list)
    done_locations: list[str] = Field(default_factory=list)
    active_routes: list[str] = Field(default_factory=list)
    active_route_locations: list[str] = Field(default_factory=list)
    updated_at: float | None = None


supervisor = FactorySupervisor(db_path=ROOT / "data" / "factory.db")
_simulation_task: asyncio.Task[None] | None = None


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global _simulation_task
    _simulation_task = asyncio.create_task(_simulation_loop())
    try:
        yield
    finally:
        _simulation_task.cancel()
        with suppress(asyncio.CancelledError):
            await _simulation_task
        _simulation_task = None


app = FastAPI(
    title="ReConFactory Digital Twin API",
    description="Fault-aware, self-reconfiguring smart factory simulation.",
    version="0.1.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


async def _simulation_loop() -> None:
    while True:
        if supervisor.running:
            supervisor.tick()
        await asyncio.sleep(AUTO_TICK_SECONDS / supervisor.simulation_speed)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/status")
async def status() -> dict[str, Any]:
    return supervisor.snapshot()


@app.get("/api/integrations")
async def integrations() -> dict[str, Any]:
    return check_integrations()


@app.get("/api/experiments/recovery")
async def recovery_experiment(product_count: int = 12) -> dict[str, Any]:
    return run_recovery_comparison(product_count=max(1, min(50, product_count)))


@app.post("/api/start")
async def start() -> dict[str, Any]:
    return supervisor.start()


@app.post("/api/stop")
async def stop() -> dict[str, Any]:
    return supervisor.stop()


@app.post("/api/reset")
async def reset(clear_database: bool = False) -> dict[str, Any]:
    return supervisor.reset(clear_database=clear_database)


@app.post("/api/emergency-stop")
async def emergency_stop() -> dict[str, Any]:
    return supervisor.emergency_stop()


@app.post("/api/products")
async def create_product(payload: ProductCreateRequest) -> dict[str, Any]:
    try:
        product = supervisor.create_product(payload.product_type, payload.defect_flags)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"product": product.to_dict(), "snapshot": supervisor.snapshot()}


@app.post("/api/tick")
async def tick(payload: TickRequest) -> dict[str, Any]:
    return supervisor.tick(payload.steps)


@app.post("/api/speed")
async def speed(payload: SpeedRequest) -> dict[str, Any]:
    return supervisor.set_speed(payload.speed)


@app.post("/api/gazebo/visuals")
async def gazebo_visuals(payload: GazeboVisualsRequest) -> dict[str, Any]:
    return supervisor.update_gazebo_visuals(payload.model_dump())


@app.post("/api/faults")
async def inject_fault(payload: FaultInjectRequest) -> dict[str, Any]:
    try:
        return supervisor.inject_fault(
            payload.machine_id, payload.fault_type, reason=payload.reason
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/recover")
async def recover(payload: RecoverRequest) -> dict[str, Any]:
    try:
        return supervisor.recover_machine(payload.machine_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.websocket("/ws")
async def websocket_status(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(supervisor.snapshot())
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        return
