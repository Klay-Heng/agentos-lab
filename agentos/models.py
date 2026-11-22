"""Shared phase 1 task models and HTTP payloads."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StringConstraints,
    field_validator,
    model_validator,
)

TaskType = Literal["demo_echo"]
Text = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=1, max_length=2000
    ),
]


class TaskStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class TaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: Text


class TaskResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: Text


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_type: TaskType
    input: TaskInput


class TaskError(BaseModel):
    """Runtime supplies a safe summary, never the raw exception traceback."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: Literal["WORKFLOW_EXECUTION_FAILED"]
    message: Annotated[str, StringConstraints(strict=True, min_length=1)]


class Task(BaseModel):
    """Validated snapshot; Runtime constructs a new snapshot for each state update."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: UUID
    thread_id: UUID
    task_type: TaskType
    status: TaskStatus
    input: TaskInput
    result: TaskResult | None = None
    error: TaskError | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        if self.task_id == self.thread_id:
            raise ValueError("task_id and thread_id must be distinct")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        if self.status == TaskStatus.SUCCEEDED:
            if self.result is None or self.error is not None:
                raise ValueError("SUCCEEDED requires result and no error")
        elif self.status == TaskStatus.FAILED:
            if self.error is None or self.result is not None:
                raise ValueError("FAILED requires error and no result")
        elif self.result is not None or self.error is not None:
            raise ValueError("Nonterminal tasks cannot contain result or error")
        return self


# Storage snapshots and API responses share one validated field definition.
TaskResponse = Task
