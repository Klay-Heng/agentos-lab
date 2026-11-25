"""Runtime integration with real task storage and controlled execution faults."""

import logging
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from agentos.contracts import TaskNotFoundError, TaskStorageError
from agentos.models import CreateTaskRequest, Task, TaskInput, TaskResult, TaskStatus
from agentos.runtime.service import InvalidTaskTransitionError, RuntimeService
from agentos.storage.tasks import SQLiteTaskRepository


@pytest.fixture
def repository(tmp_path):
    repo = SQLiteTaskRepository(tmp_path / "tasks.sqlite3")
    repo.initialize()
    return repo


def request():
    return CreateTaskRequest(task_type="demo_echo", input=TaskInput(text="hello"))


class CheckingAdapter:
    def __init__(self, repository, error=None):
        self.repository = repository
        self.error = error
        self.tasks = []

    def execute(self, task_type, input_data, thread_id):
        task = self.repository.get(self.tasks[-1].task_id)
        assert task.status == TaskStatus.RUNNING
        assert task.thread_id == thread_id
        assert task_type == task.task_type
        assert input_data == task.input
        if self.error:
            raise self.error
        return TaskResult(text=input_data.text)


def instrument(repository, monkeypatch, error=None):
    adapter = CheckingAdapter(repository, error)
    original = repository.create

    def record(task):
        saved = original(task)
        adapter.tasks.append(saved)
        return saved

    monkeypatch.setattr(repository, "create", record)
    return RuntimeService(repository, adapter), adapter


def test_success_commits_before_execution_and_logs_ids(repository, monkeypatch, caplog):
    runtime, adapter = instrument(repository, monkeypatch)
    with caplog.at_level(logging.INFO, logger="agentos.runtime.service"):
        task = runtime.create_and_run(request())
    assert task.status == TaskStatus.SUCCEEDED
    assert task.result == TaskResult(text="hello")
    assert task.task_id != task.thread_id
    assert runtime.get_task(task.task_id) == task
    assert adapter.tasks[0].status == TaskStatus.CREATED
    assert [record.status for record in caplog.records] == [
        "CREATED",
        "RUNNING",
        "SUCCEEDED",
    ]
    assert all(record.task_id == str(task.task_id) for record in caplog.records)
    assert all(record.thread_id == str(task.thread_id) for record in caplog.records)


def test_workflow_error_is_saved_with_safe_summary(repository, monkeypatch, caplog):
    runtime, _ = instrument(repository, monkeypatch, RuntimeError("secret-node-detail"))
    task = runtime.create_and_run(request())
    assert task.status == TaskStatus.FAILED
    assert task.result is None
    assert task.error.code == "WORKFLOW_EXECUTION_FAILED"
    assert "secret-node-detail" not in task.model_dump_json()
    assert runtime.get_task(task.task_id) == task
    assert "secret-node-detail" in caplog.text
    assert any(record.exc_info for record in caplog.records)


def test_checkpoint_storage_error_remains_running(repository, monkeypatch):
    failure = TaskStorageError("checkpoint unavailable")
    runtime, adapter = instrument(repository, monkeypatch, failure)
    with pytest.raises(TaskStorageError) as caught:
        runtime.create_and_run(request())
    assert caught.value is failure
    assert runtime.get_task(adapter.tasks[0].task_id).status == TaskStatus.RUNNING


@pytest.mark.parametrize(
    "failed_status", [TaskStatus.RUNNING, TaskStatus.SUCCEEDED, TaskStatus.FAILED]
)
def test_state_save_error_is_not_reported_as_success(
    repository, monkeypatch, failed_status
):
    error = RuntimeError("node failed") if failed_status == TaskStatus.FAILED else None
    runtime, adapter = instrument(repository, monkeypatch, error)
    original = repository.update_state
    failure = TaskStorageError("state save failed")

    def update(task_id, **values):
        if values["status"] == failed_status:
            raise failure
        return original(task_id, **values)

    monkeypatch.setattr(repository, "update_state", update)
    with pytest.raises(TaskStorageError) as caught:
        runtime.create_and_run(request())
    assert caught.value is failure
    expected = (
        TaskStatus.CREATED
        if failed_status == TaskStatus.RUNNING
        else TaskStatus.RUNNING
    )
    assert runtime.get_task(adapter.tasks[0].task_id).status == expected


def test_create_failure_does_not_execute_adapter(repository, monkeypatch):
    from unittest.mock import Mock

    adapter = Mock()
    failure = TaskStorageError("cannot create")
    monkeypatch.setattr(repository, "create", Mock(side_effect=failure))
    with pytest.raises(TaskStorageError):
        RuntimeService(repository, adapter).create_and_run(request())
    adapter.execute.assert_not_called()


def test_query_is_read_only_and_missing_is_not_found(repository):
    from unittest.mock import Mock

    adapter = Mock()
    runtime = RuntimeService(repository, adapter)
    missing = uuid4()
    with pytest.raises(TaskNotFoundError) as caught:
        runtime.get_task(missing)
    assert caught.value.task_id == missing
    adapter.execute.assert_not_called()


@pytest.mark.parametrize("current", list(TaskStatus))
@pytest.mark.parametrize("target", list(TaskStatus))
def test_runtime_transition_rules(repository, current, target):
    from unittest.mock import Mock

    now = datetime.now(UTC)
    values = dict(
        task_id=uuid4(),
        thread_id=uuid4(),
        task_type="demo_echo",
        status=current,
        input={"text": "hello"},
        created_at=now,
        updated_at=now,
    )
    if current == TaskStatus.SUCCEEDED:
        values["result"] = {"text": "hello"}
    if current == TaskStatus.FAILED:
        values["error"] = {"code": "WORKFLOW_EXECUTION_FAILED", "message": "failed"}
    task = repository.create(Task.model_validate(values))
    runtime = RuntimeService(repository, Mock())
    allowed = {
        (TaskStatus.CREATED, TaskStatus.RUNNING),
        (TaskStatus.RUNNING, TaskStatus.SUCCEEDED),
        (TaskStatus.RUNNING, TaskStatus.FAILED),
    }
    arguments = {}
    if target == TaskStatus.SUCCEEDED:
        arguments["result"] = TaskResult(text="hello")
    if target == TaskStatus.FAILED:
        from agentos.models import TaskError

        arguments["error"] = TaskError(
            code="WORKFLOW_EXECUTION_FAILED", message="failed"
        )
    if (current, target) in allowed:
        assert runtime._transition(task, target, **arguments).status == target
    else:
        with pytest.raises(InvalidTaskTransitionError):
            runtime._transition(task, target, **arguments)
        assert repository.get(task.task_id) == task
