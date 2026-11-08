"""FastAPI application factory."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agentos.api.health import router as health_router
from agentos.core.config import Settings
from agentos.core.logging import configure_logging

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(settings.log_level)
        logger.info("Starting %s API (%s)", settings.app_name, settings.environment)
        yield
        logger.info("Stopping %s API", settings.app_name)

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(health_router)
    return app
