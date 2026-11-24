"""Manage Task state around workflow execution without owning its resources."""

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from agentos.contracts import (
    TaskNotFoundError,
    TaskRepository,
    TaskStorageError,
    WorkflowAdapter,
)
from agentos.models import (
    CreateTaskRequest,
    Task,
    TaskError,
    TaskResult,
    TaskStatus,
)

logger = logging.getLogger(__name__)

_TRANSITIONS = {
    TaskStatus.CREATED: frozenset({TaskStatus.RUNNING}),
    TaskStatus.RUNNING: frozenset({TaskStatus.SUCCEEDED, TaskStatus.FAILED}),
    TaskStatus.SUCCEEDED: frozenset(),
    TaskStatus.FAILED: frozenset(),
}


class InvalidTaskTransitionError(ValueError):
    """Runtime rejected a transition before attempting a storage write."""


class RuntimeService:
    def __init__(self, repository: TaskRepository, adapter: WorkflowAdapter) -> None:
        self._repository = repository
        self._adapter = adapter

    def create_and_run(self, request: CreateTaskRequest) -> Task:
        now = datetime.now(UTC)
        task = self._repository.create(
            Task(
                task_id=uuid4(),
                thread_id=uuid4(),
                task_type=request.task_type,
                status=TaskStatus.CREATED,
                input=request.input,
                created_at=now,
                updated_at=now,
            )
        )
        self._log_state(task)
        task = self._transition(task, TaskStatus.RUNNING)
        try:
            result = TaskResult.model_validate(
                self._adapter.execute(task.task_type, task.input, task.thread_id)
            )
        except TaskStorageError:
            # Preserve the last committed state; storage errors are not workflow errors.
            logger.exception(
                "Storage failure task=%s thread=%s", task.task_id, task.thread_id
            )
            raise
        except Exception:
            logger.exception(
                "Workflow failure task=%s thread=%s", task.task_id, task.thread_id
            )
            return self._transition(
                task,
                TaskStatus.FAILED,
                error=TaskError(
                    code="WORKFLOW_EXECUTION_FAILED",
                    message="Workflow execution failed.",
                ),
            )
        # Persistence errors here must propagate, never fall into the workflow catch.
        return self._transition(task, TaskStatus.SUCCEEDED, result=result)

    def get_task(self, task_id: UUID) -> Task:
        task = self._repository.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        return task

    def _transition(
        self,
        task: Task,
        status: TaskStatus,
        *,
        result: TaskResult | None = None,
        error: TaskError | None = None,
    ) -> Task:
        if status not in _TRANSITIONS[task.status]:
            raise InvalidTaskTransitionError(
                f"Illegal transition: {task.status} -> {status}"
            )
        snapshot = self._repository.update_state(
            task.task_id,
            expected_status=task.status,
            status=status,
            updated_at=max(datetime.now(UTC), task.updated_at),
            result=result,
            error=error,
        )
        self._log_state(snapshot)
        return snapshot

    @staticmethod
    def _log_state(task: Task) -> None:
        logger.info(
            "Task task=%s thread=%s status=%s",
            task.task_id,
            task.thread_id,
            task.status,
            extra={
                "task_id": str(task.task_id),
                "thread_id": str(task.thread_id),
                "status": task.status.value,
            },
        )
