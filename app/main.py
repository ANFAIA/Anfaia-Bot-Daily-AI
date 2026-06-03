"""FastAPI application entry point.

Wires up the dependency container, registers the routers, and governs the
scheduler lifecycle via FastAPI's `lifespan`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.routes import discord, health, news, stats, workflow
from app.core.config import Settings, get_settings
from app.core.container import Container
from app.core.logging import configure_logging, get_logger
from app.infrastructure.scheduler.scheduler import DailyScheduler

logger = get_logger(__name__)


def create_app(settings: Settings | None = None, *, container: Container | None = None) -> FastAPI:
    """FastAPI application factory.

    Args:
        settings: configuration to use (defaults to the environment's).
        container: a prebuilt dependency container. If provided (typically in
            tests), it is reused instead of building a new one, and its
            lifecycle is managed by the caller.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    owns_container = container is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("app.starting", env=settings.app_env, version=__version__)
        active_container = container or Container(settings)
        app.state.container = active_container

        scheduler = DailyScheduler(settings, active_container.run_workflow_uc)
        scheduler.start()
        app.state.scheduler = scheduler

        try:
            yield
        finally:
            scheduler.shutdown()
            if owns_container:
                await active_container.aclose()
            logger.info("app.stopped")

    app = FastAPI(
        title="Anfaia Daily AI",
        description=(
            "Sistema autónomo multiagente que publica a diario una noticia de IA "
            "contextualizada en Discord."
        ),
        version=__version__,
        lifespan=lifespan,
    )

    app.include_router(health.router)
    app.include_router(news.router)
    app.include_router(workflow.router)
    app.include_router(discord.router)
    app.include_router(stats.router)
    return app


app = create_app()
