"""HTTP API for the dashboard and for judges poking at the system."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field

from meridian.config import StrategyParams
from meridian.core.engine import Engine


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


EngineDep = Annotated[Engine, Depends(get_engine)]


def require_control_key(
    request: Request, x_control_key: Annotated[str | None, Header()] = None
) -> None:
    expected = request.app.state.settings.control_api_key
    if expected and x_control_key != expected:
        raise HTTPException(status_code=401, detail="Missing or wrong control key.")


class ActionResult(BaseModel):
    ok: bool
    message: str


class ParamsPatch(BaseModel):
    spread_bps: Decimal | None = Field(default=None, gt=0, le=500)
    skew_bps: Decimal | None = Field(default=None, ge=0, le=500)
    order_size: int | None = Field(default=None, ge=1, le=10_000)
    max_position: int | None = Field(default=None, ge=1, le=100_000)
    requote_bps: Decimal | None = Field(default=None, ge=0, le=100)
    guard_bps: Decimal | None = Field(default=None, gt=0, le=1000)
    warn_bps: Decimal | None = Field(default=None, ge=0, le=1000)
    max_session_loss: Decimal | None = Field(default=None, gt=0)
    use_ref_drift: bool | None = None


public = APIRouter(prefix="/api", tags=["state"])
control = APIRouter(
    prefix="/api/control", tags=["control"], dependencies=[Depends(require_control_key)]
)
chaos = APIRouter(prefix="/api/chaos", tags=["chaos"], dependencies=[Depends(require_control_key)])


@public.get("/state")
async def get_state(engine: EngineDep) -> dict[str, Any]:
    return engine.state()


@public.get("/history")
async def get_history(engine: EngineDep) -> dict[str, Any]:
    return engine.history()


@public.get("/performance")
async def get_performance(engine: EngineDep) -> dict[str, Any]:
    return engine.state()["performance"]


@public.get("/decisions")
async def get_decisions(
    engine: EngineDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    kind: Literal["orders", "pause", "resume", "cancel_all"] | None = None,
) -> list[dict[str, Any]]:
    return engine.decisions.list(limit, kind)


@public.get("/events")
async def get_events(engine: EngineDep) -> list[dict[str, Any]]:
    return list(engine.events)


@public.get("/fills")
async def get_fills(engine: EngineDep, limit: int = 100) -> list[dict[str, Any]]:
    if engine.store is None:
        return []
    rows = await asyncio.to_thread(engine.store.recent_fills, min(limit, 500))
    return [r.model_dump(mode="json") for r in rows]


@public.get("/stream", response_class=EventSourceResponse)
async def stream(request: Request, engine: EngineDep) -> AsyncIterable[ServerSentEvent]:
    queue = engine.subscribe()
    try:
        yield ServerSentEvent(data=engine.state(), event="state")
        while not await request.is_disconnected():
            try:
                kind, payload = await asyncio.wait_for(queue.get(), timeout=15)
            except TimeoutError:
                yield ServerSentEvent(comment="keepalive")
                continue
            yield ServerSentEvent(data=payload, event=kind)
    finally:
        engine.unsubscribe(queue)


@control.post("/start")
async def start(engine: EngineDep) -> ActionResult:
    ok, msg = await engine.start_trading()
    if not ok:
        raise HTTPException(status_code=409, detail=msg)
    return ActionResult(ok=ok, message=msg)


@control.post("/stop")
async def stop(engine: EngineDep) -> ActionResult:
    ok, msg = await engine.stop_trading("manual stop")
    return ActionResult(ok=ok, message=msg)


@control.post("/kill")
async def kill(engine: EngineDep) -> ActionResult:
    ok, msg = await engine.kill("kill switch pressed")
    return ActionResult(ok=ok, message=msg)


@control.post("/resume")
async def resume(engine: EngineDep) -> ActionResult:
    ok, msg = await engine.resume()
    if not ok:
        raise HTTPException(status_code=409, detail=msg)
    return ActionResult(ok=ok, message=msg)


@control.post("/flatten")
async def flatten(engine: EngineDep) -> ActionResult:
    ok, msg = await engine.flatten()
    if not ok:
        raise HTTPException(status_code=409, detail=msg)
    return ActionResult(ok=ok, message=msg)


@control.patch("/params")
async def patch_params(engine: EngineDep, patch: ParamsPatch) -> StrategyParams:
    try:
        return engine.update_params(patch.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


ChaosName = Literal["stale_ref", "price_shock", "drop_feed", "ledger_drift"]


@chaos.post("/{name}")
async def run_chaos(name: ChaosName, request: Request, engine: EngineDep) -> ActionResult:
    if not request.app.state.settings.chaos_enabled:
        raise HTTPException(status_code=403, detail="Chaos actions are disabled.")
    return ActionResult(ok=True, message=await engine.chaos(name))
