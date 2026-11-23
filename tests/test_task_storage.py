"""Behavior of the phase 1 SQLite Task repository."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from agentos.contracts import (
    TaskNotFoundError,
    TaskStateConflictError,
    TaskStorageError,
)
from agentos.models import Task, TaskError, TaskInput, TaskResult, TaskStatus
from agentos.storage.tasks import SQLiteTaskRepository


def make_task(**changes: object) -> Task:
    now = datetime.now(UTC)
    values: dict[str, object] = {
        "task_id": uuid4(),
        "thread_id": uuid4(),
        "task_type": "demo_echo",
        "status": TaskStatus.CREATED,
        "input": TaskInput(text="hello AgentOS"),
        "created_at": now,
        "updated_at": now,
    }
    values.update(changes)
    return Task.model_validate(values)


@pytest.fixture
def repository(tmp_path: Path) -> SQLiteTaskRepository:
    repo = SQLiteTaskRepository(tmp_path / "state" / "tasks.sqlite3")
    repo.initialize()
    return repo


def test_initialize_creates_parent_table_and_is_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "nested" / "state" / "tasks.sqlite3"
    repo = SQLiteTaskRepository(database)

    repo.initialize()
    repo.initialize()

    assert database.is_file()
    with sqlite3.connect(database) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'tasks'"
        ).fetchone()
    assert table == ("tasks",)


def test_create_and_get_round_trip_snapshot(
    repository: SQLiteTaskRepository,
) -> None:
    task = make_task()

    assert repository.create(task) == task
    assert repository.get(task.task_id) == task


@pytest.mark.parametrize(
    ("status", "result", "error"),
    [
        (TaskStatus.CREATED, None, None),
        (TaskStatus.RUNNING, None, None),
        (TaskStatus.SUCCEEDED, TaskResult(text="done"), None),
        (
            TaskStatus.FAILED,
            None,
            TaskError(code="WORKFLOW_EXECUTION_FAILED", message="Workflow failed"),
        ),
    ],
)
def test_round_trip_preserves_status_result_and_error(
    repository: SQLiteTaskRepository,
    status: TaskStatus,
    result: TaskResult | None,
    error: TaskError | None,
) -> None:
    task = make_task(status=status, result=result, error=error)

    repository.create(task)

    assert repository.get(task.task_id) == task


def test_get_unknown_id_returns_none(repository: SQLiteTaskRepository) -> None:
    assert repository.get(uuid4()) is None


def test_snapshot_survives_reopen(tmp_path: Path) -> None:
    database = tmp_path / "tasks.sqlite3"
    task = make_task()
    first = SQLiteTaskRepository(database)
    first.initialize()
    first.create(task)

    reopened = SQLiteTaskRepository(database)
    reopened.initialize()

    assert reopened.get(task.task_id) == task


def test_tasks_do_not_overwrite_each_other(
    repository: SQLiteTaskRepository,
) -> None:
    first = make_task()
    second = make_task()

    repository.create(first)
    repository.create(second)

    assert first.task_id != second.task_id
    assert first.thread_id != second.thread_id
    assert repository.get(first.task_id) == first
    assert repository.get(second.task_id) == second


def test_duplicate_task_id_raises_storage_error(
    repository: SQLiteTaskRepository,
) -> None:
    task = make_task()
    repository.create(task)

    with pytest.raises(TaskStorageError):
        repository.create(make_task(task_id=task.task_id))

    assert repository.get(task.task_id) == task


def test_update_state_created_to_running_preserves_identity(
    repository: SQLiteTaskRepository,
) -> None:
    task = make_task()
    repository.create(task)
    updated_at = task.updated_at + timedelta(seconds=1)

    running = repository.update_state(
        task.task_id,
        expected_status=TaskStatus.CREATED,
        status=TaskStatus.RUNNING,
        updated_at=updated_at,
    )

    assert running.status == TaskStatus.RUNNING
    assert running.task_id == task.task_id
    assert running.thread_id == task.thread_id
    assert running.task_type == task.task_type
    assert running.input == task.input
    assert running.created_at == task.created_at
    assert running.updated_at == updated_at
    assert running.result is None
    assert running.error is None
    assert repository.get(task.task_id) == running


def test_update_state_persists_success_result(
    repository: SQLiteTaskRepository,
) -> None:
    task = make_task(status=TaskStatus.RUNNING)
    repository.create(task)
    result = TaskResult(text="hello AgentOS")

    succeeded = repository.update_state(
        task.task_id,
        expected_status=TaskStatus.RUNNING,
        status=TaskStatus.SUCCEEDED,
        updated_at=task.updated_at + timedelta(seconds=1),
        result=result,
    )

    assert succeeded.status == TaskStatus.SUCCEEDED
    assert succeeded.result == result
    assert succeeded.error is None
    assert repository.get(task.task_id) == succeeded


def test_update_state_persists_failure_error(
    repository: SQLiteTaskRepository,
) -> None:
    task = make_task(status=TaskStatus.RUNNING)
    repository.create(task)
    error = TaskError(code="WORKFLOW_EXECUTION_FAILED", message="Workflow failed")

    failed = repository.update_state(
        task.task_id,
        expected_status=TaskStatus.RUNNING,
        status=TaskStatus.FAILED,
        updated_at=task.updated_at + timedelta(seconds=1),
        error=error,
    )

    assert failed.status == TaskStatus.FAILED
    assert failed.error == error
    assert failed.result is None
    assert repository.get(task.task_id) == failed


def test_update_missing_task_raises_not_found(
    repository: SQLiteTaskRepository,
) -> None:
    missing = uuid4()

    with pytest.raises(TaskNotFoundError) as caught:
        repository.update_state(
            missing,
            expected_status=TaskStatus.CREATED,
            status=TaskStatus.RUNNING,
            updated_at=datetime.now(UTC),
        )

    assert caught.value.task_id == missing


def test_update_expected_status_mismatch_raises_conflict_without_writing(
    repository: SQLiteTaskRepository,
) -> None:
    task = make_task()
    repository.create(task)

    with pytest.raises(TaskStateConflictError):
        repository.update_state(
            task.task_id,
            expected_status=TaskStatus.RUNNING,
            status=TaskStatus.SUCCEEDED,
            updated_at=task.updated_at + timedelta(seconds=1),
            result=TaskResult(text="not saved"),
        )

    assert repository.get(task.task_id) == task


def test_second_update_with_stale_expected_status_conflicts(
    repository: SQLiteTaskRepository,
) -> None:
    task = make_task()
    repository.create(task)
    running = repository.update_state(
        task.task_id,
        expected_status=TaskStatus.CREATED,
        status=TaskStatus.RUNNING,
        updated_at=task.updated_at + timedelta(seconds=1),
    )

    with pytest.raises(TaskStateConflictError):
        repository.update_state(
            task.task_id,
            expected_status=TaskStatus.CREATED,
            status=TaskStatus.RUNNING,
            updated_at=task.updated_at + timedelta(seconds=2),
        )

    assert repository.get(task.task_id) == running


@pytest.mark.parametrize(
    ("status", "result", "error"),
    [
        (TaskStatus.SUCCEEDED, None, None),
        (TaskStatus.FAILED, None, None),
        (TaskStatus.RUNNING, TaskResult(text="unexpected"), None),
        (
            TaskStatus.RUNNING,
            None,
            TaskError(code="WORKFLOW_EXECUTION_FAILED", message="unexpected"),
        ),
    ],
)
def test_update_rejects_invalid_target_snapshot_without_writing(
    repository: SQLiteTaskRepository,
    status: TaskStatus,
    result: TaskResult | None,
    error: TaskError | None,
) -> None:
    task = make_task()
    repository.create(task)

    with pytest.raises(ValidationError):
        repository.update_state(
            task.task_id,
            expected_status=TaskStatus.CREATED,
            status=status,
            updated_at=task.updated_at + timedelta(seconds=1),
            result=result,
            error=error,
        )

    assert repository.get(task.task_id) == task


def test_update_rejects_updated_at_before_created_at(
    repository: SQLiteTaskRepository,
) -> None:
    task = make_task()
    repository.create(task)

    with pytest.raises(ValidationError):
        repository.update_state(
            task.task_id,
            expected_status=TaskStatus.CREATED,
            status=TaskStatus.RUNNING,
            updated_at=task.created_at - timedelta(seconds=1),
        )

    assert repository.get(task.task_id) == task


def test_repository_can_read_from_another_thread(
    repository: SQLiteTaskRepository,
) -> None:
    task = make_task()
    repository.create(task)

    with ThreadPoolExecutor(max_workers=1) as caller:
        loaded = caller.submit(repository.get, task.task_id).result(timeout=10)

    assert loaded == task


def test_create_on_uninitialized_database_raises_storage_error(
    tmp_path: Path,
) -> None:
    repo = SQLiteTaskRepository(tmp_path / "missing" / "tasks.sqlite3")

    with pytest.raises(TaskStorageError):
        repo.create(make_task())


def test_get_on_uninitialized_database_raises_storage_error(
    tmp_path: Path,
) -> None:
    repo = SQLiteTaskRepository(tmp_path / "missing" / "tasks.sqlite3")

    with pytest.raises(TaskStorageError):
        repo.get(uuid4())


def test_initialize_wraps_filesystem_errors(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    repo = SQLiteTaskRepository(blocker / "tasks.sqlite3")

    with pytest.raises(TaskStorageError):
        repo.initialize()


def test_corrupt_stored_row_raises_storage_error(tmp_path: Path) -> None:
    database = tmp_path / "tasks.sqlite3"
    repo = SQLiteTaskRepository(database)
    repo.initialize()
    task_id = uuid4()

    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(task_id),
                str(uuid4()),
                "demo_echo",
                "CREATED",
                "not-json",
                None,
                None,
                "not-a-time",
                "not-a-time",
            ),
        )

    with pytest.raises(TaskStorageError):
        repo.get(task_id)
