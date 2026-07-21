"""Graph assembly — StateGraph compiled once at import.

Phase 1 entry point is `csv_analyst` (the analyst capability slot). The
baseline `transform_text` node is still present in the module and registered
in the graph so existing harness tests keep passing; it is no longer the
entry point. See the spec/agent.md routing diagrams.
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.graph.edges import after_transform
from src.graph.nodes import csv_analyst, finalize, handle_error, transform_text
from src.graph.state import AgentState


def _build_graph():
    g = StateGraph(AgentState)
    g.add_node("transform_text", transform_text)
    g.add_node("csv_analyst", csv_analyst)
    g.add_node("handle_error", handle_error)
    g.add_node("finalize", finalize)
    g.set_entry_point("csv_analyst")
    g.add_conditional_edges(
        "transform_text",
        after_transform,
        {"finalize": "finalize", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "csv_analyst",
        after_transform,
        {"finalize": "finalize", "handle_error": "handle_error"},
    )
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()


agentic_ai = _build_graph()
