"""Real application resources: execution, persistence, cleanup and isolation."""

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import ValidationError

from agentos.contracts import TaskStorageError
from agentos.core.config import Settings
from agentos.main import create_app
from agentos.models import CreateTaskRequest, Task, TaskStatus
from agentos.storage.tasks import SQLiteTaskRepository
from agentos.workflows.demo import build_demo_echo_graph

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def settings_for(directory):
    return Settings(
        task_database_path=directory / "tasks.sqlite3",
        checkpoint_database_path=directory / "checkpoints.sqlite3",
        _env_file=None,
    )


async def test_real_runtime_reopens_without_replaying_and_closes_saver(
    tmp_path, monkeypatch
):
    settings = settings_for(tmp_path)
    connections = []
    original = SqliteSaver.from_conn_string

    @contextmanager
    def track(connection_string):
        with original(connection_string) as saver:
            connections.append(saver.conn)
            yield saver

    monkeypatch.setattr(SqliteSaver, "from_conn_string", track)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        runtime = app.state.runtime
        task = runtime.create_and_run(
            CreateTaskRequest(task_type="demo_echo", input={"text": "persisted"})
        )
        assert task.status == TaskStatus.SUCCEEDED
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get("/api/v1/health")).status_code == 200
    assert not hasattr(app.state, "runtime")
    with pytest.raises(sqlite3.ProgrammingError):
        connections[0].execute("SELECT 1")

    # Restart even the same app instance: create fresh connections and never replay.
    async with app.router.lifespan_context(app):
        assert app.state.runtime is not runtime
        assert app.state.runtime.get_task(task.task_id) == task
    with original(str(settings.checkpoint_database_path)) as saver:
        state = build_demo_echo_graph(saver).get_state(
            {"configurable": {"thread_id": str(task.thread_id)}}
        )
        assert state.values == {"text": "persisted"}
        assert state.next == ()
    with pytest.raises(sqlite3.ProgrammingError):
        connections[1].execute("SELECT 1")


async def test_apps_are_isolated(tmp_path):
    from agentos.contracts import TaskNotFoundError

    first, second = (
        create_app(settings_for(tmp_path / name)) for name in ["first", "second"]
    )
    async with (
        first.router.lifespan_context(first),
        second.router.lifespan_context(second),
    ):
        task = first.state.runtime.create_and_run(
            CreateTaskRequest(task_type="demo_echo", input={"text": "first"})
        )
        with pytest.raises(TaskNotFoundError):
            second.state.runtime.get_task(task.task_id)


@pytest.mark.parametrize("status", [TaskStatus.CREATED, TaskStatus.RUNNING])
async def test_restart_preserves_intermediate_task_without_execution(tmp_path, status):
    settings = settings_for(tmp_path)
    repository = SQLiteTaskRepository(settings.task_database_path)
    repository.initialize()
    now = datetime.now(UTC)
    task = repository.create(
        Task(
            task_id=uuid4(),
            thread_id=uuid4(),
            task_type="demo_echo",
            input={"text": "unfinished"},
            status=status,
            created_at=now,
            updated_at=now,
        )
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        assert app.state.runtime.get_task(task.task_id) == task
    with SqliteSaver.from_conn_string(str(settings.checkpoint_database_path)) as saver:
        assert (
            saver.get_tuple({"configurable": {"thread_id": str(task.thread_id)}})
            is None
        )


async def test_startup_failure_closes_acquired_saver(tmp_path, monkeypatch):
    from agentos.adapters.langgraph import LangGraphWorkflowAdapter

    connections = []
    original = SqliteSaver.from_conn_string

    @contextmanager
    def track(connection_string):
        with original(connection_string) as saver:
            connections.append(saver.conn)
            yield saver

    def fail(*args):
        raise sqlite3.OperationalError("setup failed")

    monkeypatch.setattr(SqliteSaver, "from_conn_string", track)
    monkeypatch.setattr(LangGraphWorkflowAdapter, "__init__", fail)
    app = create_app(settings_for(tmp_path))
    with pytest.raises(TaskStorageError):
        async with app.router.lifespan_context(app):
            pytest.fail("startup should fail")
    assert not hasattr(app.state, "runtime")
    with pytest.raises(sqlite3.ProgrammingError):
        connections[0].execute("SELECT 1")


async def test_shutdown_on_application_error_closes_saver(tmp_path, monkeypatch):
    connections = []
    original = SqliteSaver.from_conn_string

    @contextmanager
    def track(connection_string):
        with original(connection_string) as saver:
            connections.append(saver.conn)
            yield saver

    monkeypatch.setattr(SqliteSaver, "from_conn_string", track)
    app = create_app(settings_for(tmp_path))
    with pytest.raises(RuntimeError, match="application error"):
        async with app.router.lifespan_context(app):
            raise RuntimeError("application error")
    assert not hasattr(app.state, "runtime")
    with pytest.raises(sqlite3.ProgrammingError):
        connections[0].execute("SELECT 1")


async def test_settings_resolve_paths_and_reject_shared_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENTOS_TASK_DATABASE_PATH", "state/tasks.sqlite3")
    monkeypatch.setenv("AGENTOS_CHECKPOINT_DATABASE_PATH", "state/checkpoints.sqlite3")
    settings = Settings(_env_file=None)
    assert settings.task_database_path == tmp_path / "state/tasks.sqlite3"
    assert settings.checkpoint_database_path == tmp_path / "state/checkpoints.sqlite3"
    with pytest.raises(ValidationError):
        Settings(
            task_database_path="same.sqlite3",
            checkpoint_database_path="./same.sqlite3",
            _env_file=None,
        )
