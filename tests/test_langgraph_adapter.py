"""Behavior of the LangGraph adapter against the WorkflowAdapter contract."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agentos.adapters.langgraph import LangGraphWorkflowAdapter
from agentos.contracts import TaskStorageError
from agentos.models import TaskInput, TaskResult
from agentos.workflows.demo import build_demo_echo_graph


def test_execute_returns_result_and_persists_under_caller_thread(
    tmp_path: Path,
) -> None:
    database = tmp_path / "checkpoints.sqlite3"
    thread_id = uuid4()

    with SqliteSaver.from_conn_string(database) as saver:
        adapter = LangGraphWorkflowAdapter(saver)
        result = adapter.execute(
            "demo_echo", TaskInput(text="hello AgentOS"), thread_id
        )

    assert result == TaskResult(text="hello AgentOS")

    config = {"configurable": {"thread_id": str(thread_id)}}
    with SqliteSaver.from_conn_string(database) as reopened:
        state = build_demo_echo_graph(reopened).get_state(config)
    assert state.values == {"text": "hello AgentOS"}
    assert state.next == ()


def test_execute_reuses_adapter_from_sync_route_worker_threads(
    tmp_path: Path,
) -> None:
    """Sync FastAPI routes call the adapter on threadpool workers, reusing
    one adapter and one checkpointer across many tasks."""
    database = tmp_path / "checkpoints.sqlite3"
    jobs = [
        (TaskInput(text="first"), uuid4()),
        (TaskInput(text="second"), uuid4()),
    ]

    with SqliteSaver.from_conn_string(database) as saver:
        adapter = LangGraphWorkflowAdapter(saver)
        with ThreadPoolExecutor(max_workers=1) as caller:
            results = [
                caller.submit(adapter.execute, "demo_echo", data, thread).result(
                    timeout=10
                )
                for data, thread in jobs
            ]

    assert results == [TaskResult(text="first"), TaskResult(text="second")]
    with SqliteSaver.from_conn_string(database) as reopened:
        graph = build_demo_echo_graph(reopened)
        for data, thread in jobs:
            config = {"configurable": {"thread_id": str(thread)}}
            assert graph.get_state(config).values == {"text": data.text}


def test_node_exception_propagates_to_caller(tmp_path: Path) -> None:
    class BoomState(TypedDict):
        text: str

    def raise_node(state: BoomState) -> BoomState:
        raise RuntimeError("node exploded")

    with SqliteSaver.from_conn_string(tmp_path / "checkpoints.sqlite3") as saver:
        builder = StateGraph(BoomState)
        builder.add_node("boom", raise_node)
        builder.add_edge(START, "boom")
        builder.add_edge("boom", END)
        failing_graph: CompiledStateGraph = builder.compile(checkpointer=saver)
        adapter = LangGraphWorkflowAdapter(saver, graphs={"demo_echo": failing_graph})

        with pytest.raises(RuntimeError, match="node exploded"):
            adapter.execute("demo_echo", TaskInput(text="boom"), uuid4())


def test_sqlite_failure_wrapped_as_storage_error(tmp_path: Path) -> None:
    connection = sqlite3.connect(
        tmp_path / "checkpoints.sqlite3", check_same_thread=False
    )
    saver = SqliteSaver(connection)
    adapter = LangGraphWorkflowAdapter(
        saver, graphs={"demo_echo": build_demo_echo_graph(saver)}
    )
    connection.close()

    with pytest.raises(TaskStorageError):
        adapter.execute("demo_echo", TaskInput(text="offline"), uuid4())


def test_unknown_task_type_is_rejected(tmp_path: Path) -> None:
    with SqliteSaver.from_conn_string(tmp_path / "checkpoints.sqlite3") as saver:
        adapter = LangGraphWorkflowAdapter(saver)

        with pytest.raises(ValueError, match="Unsupported task type"):
            adapter.execute("other_type", TaskInput(text="x"), uuid4())  # type: ignore[arg-type]
