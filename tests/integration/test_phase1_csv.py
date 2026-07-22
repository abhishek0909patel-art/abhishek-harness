"""Phase 1 integration gate for the CSV analyst capability."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.analyst.metadata_engine import load_csv, schema_block
from src.analyst.sandbox import run_sandbox
from src.graph.agent import agentic_ai
from src.graph.state import AgentState

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _load_case_status(tmp_path: Path):
    src = FIXTURE_DIR / "case_status.csv"
    dest = tmp_path / "case_status.csv"
    dest.write_bytes(src.read_bytes())
    df = pd.read_csv(dest)
    meta = load_csv(dest, session_id="case-status-session")
    return dest, df, meta


def test_metadata_engine_loads_csv(tmp_path: Path):
    _, df, meta = _load_case_status(tmp_path)
    assert meta.row_count == len(df)
    assert any(column.name == "station" for column in meta.columns)
    block = schema_block(meta)
    assert "station" in block


def test_sandbox_runs_groupby_case_status(tmp_path: Path):
    _, df, meta = _load_case_status(tmp_path)
    code = "result = df.groupby('station')['count'].sum().reset_index()"
    res = run_sandbox(code, {"df": df})
    assert res.ok
    assert res.dataframe is not None
    rows = {row["station"]: row["count"] for row in res.dataframe}
    assert rows.get("Lucknow") == 1
    assert rows.get("Kanpur") == 1


def test_graph_runs_case_status_question(tmp_path: Path):
    _, df, meta = _load_case_status(tmp_path)
    state: AgentState = {
        "run_id": "case-status-test",
        "input_text": "group by station and sum count",
        "instruction": "group by station and sum count",
        "datasets": [meta],
        "_dataframes": {"df": df},
        "generated_code": "result = df.head(3)",
        "error": None,
    }
    out = agentic_ai.invoke(state)
    assert out.get("status") == "completed"
    assert out.get("output_table") is not None
    code = out.get("generated_code") or ""
    assert "result =" in code
    assert "import" not in code
