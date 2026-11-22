"""Validate the contract before storage, Runtime, and API implementations exist."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from agentos.models import (
    CreateTaskRequest,
    Task,
    TaskError,
    TaskInput,
    TaskResponse,
    TaskResult,
    TaskStatus,
)


def snapshot(**changes):
    now = datetime.now(UTC)
    values = {
        "task_id": uuid4(),
        "thread_id": uuid4(),
        "task_type": "demo_echo",
        "status": TaskStatus.CREATED,
        "input": {"text": "hello AgentOS"},
        "created_at": now,
        "updated_at": now,
    }
    values.update(changes)
    return Task.model_validate(values)


def test_request_normalizes_text_and_accepts_limit():
    request = CreateTaskRequest.model_validate(
        {"task_type": "demo_echo", "input": {"text": "  hello AgentOS\n"}}
    )
    assert request.input.text == "hello AgentOS"
    assert TaskInput(text="x" * 2000).text == "x" * 2000


@pytest.mark.parametrize("text", ["", " \t\n", "x" * 2001, None, 123, True, [], {}])
def test_invalid_text_rejected(text):
    with pytest.raises(ValidationError):
        CreateTaskRequest(task_type="demo_echo", input={"text": text})


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"input": {"text": "hello"}},
        {"task_type": "demo_echo"},
        {"task_type": "unknown", "input": {"text": "hello"}},
        {"task_type": "demo_echo", "input": {}},
        {"task_type": "demo_echo", "input": {"text": "hello", "force_fail": True}},
        {"task_type": "demo_echo", "input": {"text": "hello"}, "task_id": str(uuid4())},
    ],
)
def test_request_rejects_missing_unknown_and_server_owned_fields(payload):
    with pytest.raises(ValidationError):
        CreateTaskRequest.model_validate(payload)


@pytest.mark.parametrize("status", [TaskStatus.CREATED, TaskStatus.RUNNING])
def test_nonterminal_snapshot_serialization(status):
    task = snapshot(status=status)
    data = task.model_dump(mode="json")
    assert TaskResponse is Task
    assert data["status"] == status.value
    assert data["task_id"] == str(task.task_id)
    assert data["thread_id"] == str(task.thread_id)
    assert data["input"] == {"text": "hello AgentOS"}
    assert data["result"] is None and data["error"] is None
    assert data["created_at"].endswith("Z")
    assert Task.model_validate_json(task.model_dump_json()) == task


def test_success_and_failure_snapshots():
    succeeded = snapshot(status="SUCCEEDED", result=TaskResult(text="hello AgentOS"))
    failed = snapshot(
        status="FAILED",
        error=TaskError(code="WORKFLOW_EXECUTION_FAILED", message="Workflow failed"),
    )
    assert succeeded.model_dump(mode="json")["result"] == {"text": "hello AgentOS"}
    assert failed.model_dump(mode="json")["error"] == {
        "code": "WORKFLOW_EXECUTION_FAILED",
        "message": "Workflow failed",
    }


@pytest.mark.parametrize(
    ("status", "result", "error"),
    [
        ("SUCCEEDED", None, None),
        (
            "SUCCEEDED",
            {"text": "ok"},
            {"code": "WORKFLOW_EXECUTION_FAILED", "message": "x"},
        ),
        ("FAILED", None, None),
        (
            "FAILED",
            {"text": "ok"},
            {"code": "WORKFLOW_EXECUTION_FAILED", "message": "x"},
        ),
        ("CREATED", {"text": "ok"}, None),
        ("RUNNING", None, {"code": "WORKFLOW_EXECUTION_FAILED", "message": "x"}),
    ],
)
def test_inconsistent_snapshots_rejected(status, result, error):
    with pytest.raises(ValidationError):
        snapshot(status=status, result=result, error=error)


def test_uuid_and_time_constraints():
    same_id = uuid4()
    now = datetime.now(UTC)
    for changes in [
        {"task_id": "invalid"},
        {"task_id": same_id, "thread_id": same_id},
        {"created_at": datetime(2026, 11, 22)},
        {"created_at": now, "updated_at": now - timedelta(seconds=1)},
    ]:
        with pytest.raises(ValidationError):
            snapshot(**changes)

    local = datetime(2026, 11, 22, 8, tzinfo=timezone(timedelta(hours=8)))
    task = snapshot(created_at=local, updated_at=local)
    assert task.created_at == datetime(2026, 11, 22, tzinfo=UTC)
    assert task.created_at.tzinfo == UTC


def test_snapshot_cannot_be_mutated():
    task = snapshot()
    with pytest.raises(ValidationError):
        task.status = TaskStatus.RUNNING
    with pytest.raises(ValidationError):
        task.input.text = "changed"
