import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import containers as containers_api
from app.api import disks as disks_api
from app.api import events as events_api
from app.api import health, nodes
from app.api import metrics as metrics_api
from app.bus import EventBus
from app.config import settings
from app.db import init_engine
from app.events import events_recorder
from app.metrics.store import MetricsStore
from app.ws import agent_ws, ui_ws
from app.ws.registry import AgentRegistry

logger = logging.getLogger("bifrost")


def run_migrations() -> None:
    from alembic.config import Config

    from alembic import command

    ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{settings.state_db_path}")
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        init_engine()
        run_migrations()

        app.state.bus = EventBus()
        app.state.agent_registry = AgentRegistry()
        app.state.metrics = MetricsStore(
            settings.metrics_db_path,
            retention={
                "raw": settings.retention_raw_h * 3600,
                "1m": settings.retention_1m_d * 86400,
                "1h": settings.retention_1h_d * 86400,
            },
        )
        await app.state.metrics.start()

        tasks = [
            asyncio.create_task(events_recorder(app.state.bus), name="events-recorder"),
            asyncio.create_task(agent_ws.heartbeat_monitor(app.state), name="heartbeat-monitor"),
        ]
        logger.info("bifrost hub up — data dir %s", settings.data_dir)
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await app.state.metrics.stop()

    app = FastAPI(title="bifrost-hub", lifespan=lifespan)

    api_prefix = "/api/v1"
    app.include_router(health.router, prefix=api_prefix)
    app.include_router(nodes.router, prefix=api_prefix)
    app.include_router(containers_api.router, prefix=api_prefix)
    app.include_router(disks_api.router, prefix=api_prefix)
    app.include_router(metrics_api.router, prefix=api_prefix)
    app.include_router(events_api.router, prefix=api_prefix)
    app.include_router(agent_ws.router)
    app.include_router(ui_ws.router)

    dist = settings.frontend_dist
    if dist.is_dir() and (dist / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(dist):
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app
