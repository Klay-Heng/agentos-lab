"""Compatibility smoke test only; no AgentOS workflow or Adapter implementation."""

from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph


class DependencyState(TypedDict):
    value: int


def test_sync_graph_and_sqlite_checkpoint_compatible(tmp_path):
    builder = StateGraph(DependencyState)
    builder.add_node("increment", lambda state: {"value": state["value"] + 1})
    builder.add_edge(START, "increment")
    builder.add_edge("increment", END)
    database = str(tmp_path / "dependency-check.sqlite3")
    config = {"configurable": {"thread_id": "dependency-smoke"}}

    with SqliteSaver.from_conn_string(database) as saver:
        graph = builder.compile(checkpointer=saver)
        # The saver is owned by application startup, called from a sync-route thread.
        with ThreadPoolExecutor(max_workers=1) as caller:
            result = caller.submit(graph.invoke, {"value": 1}, config).result(
                timeout=10
            )
        assert result["value"] == 2

    with SqliteSaver.from_conn_string(database) as reopened:
        saved = builder.compile(checkpointer=reopened).get_state(config)
        assert saved.values == {"value": 2}
