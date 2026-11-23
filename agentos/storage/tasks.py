"""SQLite persistence for phase 1 task snapshots.

Connections are short-lived and created per operation, so the repository can be
called from the synchronous route threads used by the API. The repository only
enforces conditional writes and snapshot validity; legal status transitions
remain the Runtime's responsibility.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from uuid import UUID

from agentos.contracts import (
    TaskNotFoundError,
    TaskStateConflictError,
    TaskStorageError,
)
from agentos.models import Task, TaskError, TaskInput, TaskResult, TaskStatus

_SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    status TEXT NOT NULL,
    input_json TEXT NOT NULL,
    result_json TEXT,
    error_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_COLUMNS: Final = (
    "task_id, thread_id, task_type, status, input_json, "
    "result_json, error_json, created_at, updated_at"
)

_INSERT: Final = (
    "INSERT INTO tasks (task_id, thread_id, task_type, status, input_json, "
    "result_json, error_json, created_at, updated_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_UPDATE: Final = (
    "UPDATE tasks SET status = ?, updated_at = ?, result_json = ?, "
    "error_json = ? WHERE task_id = ? AND status = ?"
)


class SQLiteTaskRepository:
    """Store validated task snapshots in a dedicated SQLite file."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)

    def initialize(self) -> None:
        """Create the parent directory and tasks table; safe to repeat."""
        try:
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as connection:
                connection.execute(_SCHEMA)
                connection.commit()
        except (OSError, sqlite3.Error) as exc:
            raise TaskStorageError(
                f"Could not initialize task database at {self._database_path}"
            ) from exc

    def create(self, task: Task) -> Task:
        try:
            with closing(self._connect()) as connection:
                connection.execute(_INSERT, _row_values(task))
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise TaskStorageError(f"Task {task.task_id} already exists") from exc
        except sqlite3.Error as exc:
            raise TaskStorageError(f"Could not store task {task.task_id}") from exc
        return task

    def get(self, task_id: UUID) -> Task | None:
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    f"SELECT {_COLUMNS} FROM tasks WHERE task_id = ?",
                    (str(task_id),),
                ).fetchone()
        except sqlite3.Error as exc:
            raise TaskStorageError(f"Could not read task {task_id}") from exc

        if row is None:
            return None
        try:
            return _task_from_row(row)
        except (TypeError, ValueError) as exc:
            raise TaskStorageError(f"Stored task {task_id} is invalid") from exc

    def update_state(
        self,
        task_id: UUID,
        *,
        expected_status: TaskStatus,
        status: TaskStatus,
        updated_at: datetime,
        result: TaskResult | None = None,
        error: TaskError | None = None,
    ) -> Task:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM tasks WHERE task_id = ?",
                (str(task_id),),
            ).fetchone()
            if row is None:
                raise TaskNotFoundError(task_id)

            try:
                current = _task_from_row(row)
            except (TypeError, ValueError) as exc:
                raise TaskStorageError(f"Stored task {task_id} is invalid") from exc
            if current.status != expected_status:
                raise TaskStateConflictError(
                    f"Task {task_id} is {current.status}, expected {expected_status}"
                )

            snapshot = Task.model_validate(
                {
                    **current.model_dump(),
                    "status": status,
                    "updated_at": updated_at,
                    "result": result,
                    "error": error,
                }
            )
            cursor = connection.execute(
                _UPDATE,
                (
                    snapshot.status.value,
                    _format_time(snapshot.updated_at),
                    _dump_optional(snapshot.result),
                    _dump_optional(snapshot.error),
                    str(task_id),
                    expected_status.value,
                ),
            )
            if cursor.rowcount != 1:
                raise TaskStateConflictError(f"Task {task_id} changed while updating")
            connection.commit()
            return snapshot
        except BaseException as exc:
            _rollback(connection)
            if isinstance(exc, sqlite3.Error):
                raise TaskStorageError(f"Could not update task {task_id}") from exc
            raise
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(
            self._database_path,
            timeout=5.0,
            isolation_level=None,
        )


def _rollback(connection: sqlite3.Connection) -> None:
    try:
        connection.rollback()
    except sqlite3.Error:
        pass


def _row_values(task: Task) -> tuple[object, ...]:
    return (
        str(task.task_id),
        str(task.thread_id),
        task.task_type,
        task.status.value,
        task.input.model_dump_json(),
        _dump_optional(task.result),
        _dump_optional(task.error),
        _format_time(task.created_at),
        _format_time(task.updated_at),
    )


def _task_from_row(row: tuple[object, ...]) -> Task:
    (
        task_id,
        thread_id,
        task_type,
        status,
        input_json,
        result_json,
        error_json,
        created_at,
        updated_at,
    ) = row
    return Task.model_validate(
        {
            "task_id": task_id,
            "thread_id": thread_id,
            "task_type": task_type,
            "status": status,
            "input": TaskInput.model_validate_json(input_json),
            "result": (
                TaskResult.model_validate_json(result_json)
                if result_json is not None
                else None
            ),
            "error": (
                TaskError.model_validate_json(error_json)
                if error_json is not None
                else None
            ),
            "created_at": datetime.fromisoformat(created_at),
            "updated_at": datetime.fromisoformat(updated_at),
        }
    )


def _dump_optional(value: TaskResult | TaskError | None) -> str | None:
    return value.model_dump_json() if value is not None else None


def _format_time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()
