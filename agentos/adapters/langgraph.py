"""LangGraph adapter implementing the synchronous WorkflowAdapter contract.

LangGraph types, graph configuration, and checkpointer access stay inside this
module and the workflow modules; the Runtime and API layers only see the
contract types. The adapter never owns the checkpointer lifecycle: it receives
an already-open saver from the application composition root and must not close
it.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from agentos.contracts import TaskStorageError
from agentos.models import TaskInput, TaskResult, TaskType
from agentos.workflows.demo import build_demo_echo_graph


class LangGraphWorkflowAdapter:
    """Execute real LangGraph workflows behind the WorkflowAdapter contract."""

    def __init__(
        self,
        checkpointer: BaseCheckpointSaver,
        graphs: Mapping[str, CompiledStateGraph] | None = None,
    ) -> None:
        """Bind task types to graphs compiled on the shared checkpointer.

        ``graphs`` allows tests to substitute graphs (for example failing
        nodes); production callers pass only the checkpointer.
        """
        if graphs is None:
            graphs = {"demo_echo": build_demo_echo_graph(checkpointer)}
        self._graphs: dict[str, CompiledStateGraph] = dict(graphs)

    def execute(
        self, task_type: TaskType, input_data: TaskInput, thread_id: UUID
    ) -> TaskResult:
        """Run the graph under the caller-provided thread_id.

        Uses ``str(thread_id)`` verbatim in the graph config so checkpoints
        land on the Runtime-assigned execution context. Node exceptions
        propagate unchanged; checkpoint I/O failures surface as
        TaskStorageError. Classification boundary: any ``sqlite3.Error``
        raised during invoke is treated as checkpoint I/O failure — safe
        here because demo_echo nodes perform no SQLite access of their own.
        """
        graph = self._graphs.get(task_type)
        if graph is None:
            raise ValueError(f"Unsupported task type: {task_type!r}")
        config = {"configurable": {"thread_id": str(thread_id)}}
        try:
            final_state = graph.invoke({"text": input_data.text}, config)
        except sqlite3.Error as exc:
            raise TaskStorageError(
                f"Checkpoint persistence failed for thread {thread_id}"
            ) from exc
        return TaskResult.model_validate(final_state)
