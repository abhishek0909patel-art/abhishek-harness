"""Phase 1 integration gate for the CSV analyst capability."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.analyst.metadata_engine import load_csv, schema_block
from src.analyst.sandbox import run_sandbox
from src.graph.agent import agentic_ai
from src.graph.state import AgentState


@pytest.fixture()
def sample_dataset(tmp_path: Path):
    df = pd.DataFrame(
        {
            "station": ["Chattra", "Lucknow", "Kanpur", "Lucknow", "Kanpur"],
            "date": pd.to_datetime(
                [
                    "2025-01-02",
                    "2025-01-03",
                    "2025-01-04",
                    "2025-01-05",
                    "2025-01-06",
                ]
            ),
            "section": ["279", "279", "279", "302", "302"],
            "count": [1, 1, 1, 1, 1],
        }
    )
    path = tmp_path / "UserReport.csv"
    df.to_csv(path, index=False)
    meta = load_csv(path, session_id="s1")
    return path, df, meta


def test_metadata_engine_loads_csv(sample_dataset):
    path, df, meta = sample_dataset
    assert meta.row_count == 5
    assert meta.column_count == 4
    assert any(column.name == "station" for column in meta.columns)
    block = schema_block(meta)
    assert "station" in block
    assert "Lucknow" in block


def test_sandbox_runs_groupby(sample_dataset):
    path, df, meta = sample_dataset
    code = "result = df.groupby('station')['count'].sum().reset_index()"
    res = run_sandbox(code, {"df": df})
    assert res.ok
    assert res.dataframe is not None
    rows = {row["station"]: row["count"] for row in res.dataframe}
    assert rows["Lucknow"] == 2
    assert rows["Kanpur"] == 2
    assert rows["Chattra"] == 1


def test_graph_runs_csv_question(sample_dataset):
    path, df, meta = sample_dataset
    state: AgentState = {
        "run_id": "test",
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
    assert out.get("generated_code") == "result = df.head(3)"
