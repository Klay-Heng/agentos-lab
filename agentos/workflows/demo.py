"""Deterministic demo_echo workflow for the phase 1 minimal execution loop.

The graph is intentionally trivial: one node echoes the input text so the
Runtime closed loop can be exercised without models, network, or external
services.
"""

from typing import TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph


class DemoEchoState(TypedDict):
    """Single-channel state carried through the demo_echo graph."""

    text: str


def _echo(state: DemoEchoState) -> DemoEchoState:
    return {"text": state["text"]}


def build_demo_echo_graph(checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    """Compile the demo_echo graph bound to the caller-owned checkpointer."""
    builder = StateGraph(DemoEchoState)
    builder.add_node("echo", _echo)
    builder.add_edge(START, "echo")
    builder.add_edge("echo", END)
    return builder.compile(checkpointer=checkpointer)
