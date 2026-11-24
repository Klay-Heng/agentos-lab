"""FastAPI application factory."""

import logging
import sqlite3
from contextlib import ExitStack, asynccontextmanager

from fastapi import FastAPI
from langgraph.checkpoint.sqlite import SqliteSaver

from agentos.adapters.langgraph import LangGraphWorkflowAdapter
from agentos.api.health import router as health_router
from agentos.contracts import TaskStorageError
from agentos.core.config import Settings
from agentos.core.logging import configure_logging
from agentos.runtime.service import RuntimeService
from agentos.storage.tasks import SQLiteTaskRepository

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(settings.log_level)
        logger.info("Starting %s API (%s)", settings.app_name, settings.environment)
        with ExitStack() as resources:
            try:
                repository = SQLiteTaskRepository(settings.task_database_path)
                repository.initialize()
                settings.checkpoint_database_path.parent.mkdir(
                    parents=True, exist_ok=True
                )
                saver = resources.enter_context(
                    SqliteSaver.from_conn_string(str(settings.checkpoint_database_path))
                )
                saver.setup()
                adapter = LangGraphWorkflowAdapter(saver)
            except (OSError, sqlite3.Error) as exc:
                raise TaskStorageError("Could not initialize runtime storage") from exc
            app.state.runtime = RuntimeService(repository, adapter)
            try:
                yield
            finally:
                del app.state.runtime
                logger.info("Stopping %s API", settings.app_name)

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(health_router)
    return app
