"""AgentState — the TypedDict flowing through the graph (baseline + analyst)."""
from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    input_text: str
    instruction: str
    output_text: str
    provider: str
    model: str
    status: str
    error: str | None
    # --- analyst additions ---
    source: str | None # "csv" | "db" | "unknown"
    datasets: list[str] | None
    schema_block: str | None
    generated_code: str | None
    exec_result: dict[str, Any] | None
    retries: int | None
    followups: list[str] | None
    output_table: list[dict[str, Any]] | None
    output_chart: dict[str, Any] | None
    output_text: str | None
    audit: dict[str, Any] | None
    _dataframes: dict[str, Any] | None
