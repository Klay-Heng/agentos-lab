"""Synchronous ports for phase 1 implementations and test doubles.

These protocols contain no storage, workflow, or task execution implementation.
"""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from agentos.models import (
    CreateTaskRequest,
    Task,
    TaskError,
    TaskInput,
    TaskResponse,
    TaskResult,
    TaskStatus,
    TaskType,
)


class TaskNotFoundError(LookupError):
    """Runtime or an update could not find a task; API maps this to 404."""

    def __init__(self, task_id: UUID) -> None:
        self.task_id = task_id
        super().__init__(f"Task {task_id} was not found")


class TaskStorageError(RuntimeError):
    """Task or checkpoint persistence failed; API maps this to 503."""


class TaskStateConflictError(TaskStorageError):
    """Stored state changed before a conditional update; do not overwrite it."""


class TaskRepository(Protocol):
    def create(self, task: Task) -> Task:
        """Commit and return the snapshot; duplicate IDs raise TaskStorageError."""
        ...

    def get(self, task_id: UUID) -> Task | None:
        """Return a persisted snapshot or None; I/O errors raise TaskStorageError."""
        ...

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
        """Commit a validated snapshot with an atomic expected-status check.

        Missing ID raises TaskNotFoundError; mismatch raises TaskStateConflictError.
        Runtime owns legal transition rules; Repository preserves IDs/input/created_at.
        """
        ...


class WorkflowAdapter(Protocol):
    def execute(
        self, task_type: TaskType, input_data: TaskInput, thread_id: UUID
    ) -> TaskResult:
        """Use str(thread_id) for graph config; return only the business result.

        Propagate node exceptions to Runtime. Wrap checkpoint I/O failures in
        TaskStorageError so they are not mislabeled as ordinary workflow failures.
        """
        ...


class TaskRuntime(Protocol):
    def create_and_run(self, request: CreateTaskRequest) -> TaskResponse:
        """Return a saved SUCCEEDED/FAILED task, or raise TaskStorageError.

        Caller injects a Repository and Adapter into the concrete Runtime.
        """
        ...

    def get_task(self, task_id: UUID) -> TaskResponse:
        """Read without executing; raise TaskNotFoundError or TaskStorageError."""
        ...
