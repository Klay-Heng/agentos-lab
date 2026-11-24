"""Behavior of the deterministic demo_echo workflow graph."""

from pathlib import Path
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver

from agentos.workflows.demo import build_demo_echo_graph


def test_echo_returns_input_text(tmp_path: Path) -> None:
    database = tmp_path / "checkpoints.sqlite3"

    with SqliteSaver.from_conn_string(database) as saver:
        graph = build_demo_echo_graph(saver)
        config = {"configurable": {"thread_id": str(uuid4())}}
        result = graph.invoke({"text": "hello AgentOS"}, config)

    assert result == {"text": "hello AgentOS"}


def test_checkpoint_readable_via_public_interface(tmp_path: Path) -> None:
    database = tmp_path / "checkpoints.sqlite3"

    with SqliteSaver.from_conn_string(database) as saver:
        graph = build_demo_echo_graph(saver)
        config = {"configurable": {"thread_id": str(uuid4())}}
        graph.invoke({"text": "persisted"}, config)
        state = graph.get_state(config)

    assert state.values == {"text": "persisted"}
    assert state.next == ()


def test_checkpoint_survives_saver_reopen(tmp_path: Path) -> None:
    database = tmp_path / "checkpoints.sqlite3"
    config = {"configurable": {"thread_id": str(uuid4())}}

    with SqliteSaver.from_conn_string(database) as saver:
        build_demo_echo_graph(saver).invoke({"text": "reopened"}, config)

    with SqliteSaver.from_conn_string(database) as reopened:
        state = build_demo_echo_graph(reopened).get_state(config)

    assert state.values == {"text": "reopened"}
    assert state.next == ()


def test_different_threads_are_isolated(tmp_path: Path) -> None:
    database = tmp_path / "checkpoints.sqlite3"

    with SqliteSaver.from_conn_string(database) as saver:
        graph = build_demo_echo_graph(saver)
        config_a = {"configurable": {"thread_id": str(uuid4())}}
        config_b = {"configurable": {"thread_id": str(uuid4())}}
        graph.invoke({"text": "first"}, config_a)
        graph.invoke({"text": "second"}, config_b)

        assert graph.get_state(config_a).values == {"text": "first"}
        assert graph.get_state(config_b).values == {"text": "second"}
