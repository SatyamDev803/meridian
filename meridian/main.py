"""App factory. One process serves the API, the live stream and the built dashboard."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from meridian.api.routes import chaos, control, public
from meridian.config import Settings
from meridian.core.engine import Engine
from meridian.storage.db import Store, make_engine


def create_app(settings: Settings | None = None, *, start_engine: bool = True) -> FastAPI:
    settings = settings or Settings()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = Store(make_engine(settings.database_url))
        engine = Engine(settings, store)
        app.state.engine = engine
        if start_engine:
            await engine.start()
        try:
            yield
        finally:
            await engine.shutdown()

    app = FastAPI(title="Meridian", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["state"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(public)
    app.include_router(control)
    app.include_router(chaos)

    web = Path(settings.web_dir)
    if web.is_dir():
        app.frontend("/", directory=str(web))
    return app


app = create_app()
