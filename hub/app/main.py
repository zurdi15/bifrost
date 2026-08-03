import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.alerts.engine import alerts_engine
from app.api import alerts as alerts_api
from app.api import bookmarks as bookmarks_api
from app.api import containers as containers_api
from app.api import disks as disks_api
from app.api import events as events_api
from app.api import gateway as gateway_api
from app.api import health, nodes
from app.api import icons as icons_api
from app.api import k8s as k8s_api
from app.api import metrics as metrics_api
from app.api import widgets as widgets_api
from app.bookmarks_file import bookmarks_file_watcher
from app.bus import EventBus
from app.checks.runner import checks_runner
from app.checks.services import service_checks
from app.config import settings
from app.db import init_engine
from app.events import events_recorder
from app.k8s.watcher import K8sManager
from app.metrics.store import MetricsStore
from app.updates.watcher import update_watch
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

        app.state.k8s_manager = K8sManager(app.state.bus)
        await app.state.k8s_manager.start()

        tasks = [
            asyncio.create_task(events_recorder(app.state.bus), name="events-recorder"),
            asyncio.create_task(agent_ws.heartbeat_monitor(app.state), name="heartbeat-monitor"),
            asyncio.create_task(checks_runner(app.state), name="checks-runner"),
            asyncio.create_task(alerts_engine(app.state.bus), name="alerts-engine"),
            asyncio.create_task(service_checks(app.state.bus), name="service-checks"),
            asyncio.create_task(update_watch(app.state.bus), name="update-watch"),
            asyncio.create_task(
                bookmarks_file_watcher(app.state.bus), name="bookmarks-file"
            ),
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
            await app.state.k8s_manager.stop()
            await app.state.metrics.stop()

    app = FastAPI(title="bifrost-hub", lifespan=lifespan)

    api_prefix = "/api/v1"
    app.include_router(health.router, prefix=api_prefix)
    app.include_router(nodes.router, prefix=api_prefix)
    app.include_router(containers_api.router, prefix=api_prefix)
    app.include_router(disks_api.router, prefix=api_prefix)
    app.include_router(k8s_api.router, prefix=api_prefix)
    app.include_router(gateway_api.router, prefix=api_prefix)
    app.include_router(widgets_api.router, prefix=api_prefix)
    app.include_router(icons_api.router, prefix=api_prefix)
    app.include_router(bookmarks_api.router, prefix=api_prefix)
    app.include_router(alerts_api.router, prefix=api_prefix)
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
