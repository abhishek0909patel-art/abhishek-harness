"""Analyst API — upload CSVs, query, list datasets."""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.analyst.metadata_engine import DatasetMeta, load_csv, schema_block
from src.analyst.sandbox import SandboxResult, run_sandbox
from src.analyst.schema_retriever import retrieve_schema
from src.db.session import get_session
from src.graph.state import AgentState
from src.graph.runner import run_agent

router = APIRouter()

_UPLOAD_ROOT = Path(
    os.environ.get("UP_ANALYST_UPLOAD_ROOT", "./data/uploads")
)


class QueryRequest(BaseModel):
    question: str
    dataset_ids: list[int] | None = None


class DatasetInfo(BaseModel):
    id: int
    filename: str
    row_count: int
    column_count: int
    uploaded_at: str


class QueryResponse(BaseModel):
    output_table: list[dict[str, Any]] | None
    output_columns: list[str] | None
    output_chart: dict[str, Any] | None
    output_text: str | None
    generated_code: str | None
    followups: list[str] | None
    error: str | None
    status: str


@router.post("/analyst/upload", response_model=list[DatasetInfo])
def upload_datasets(
    files: list[UploadFile] = File(...),
    session=Depends(get_session),
):
    _UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    session_id = uuid.uuid4().hex
    results: list[DatasetInfo] = []
    for upload in files:
        if not upload.filename.lower().endswith(".csv"):
            raise HTTPException(
                status_code=400,
                detail=f"{upload.filename}: only .csv files are accepted",
            )
        dest = _UPLOAD_ROOT / session_id / upload.filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        content = upload.file.read()
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"{upload.filename}: exceeds 50 MB limit",
            )
        dest.write_bytes(content)
        try:
            meta = load_csv(dest, session_id=session_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=422,
                detail=f"{upload.filename}: parse error — {exc}",
            ) from exc
        results.append(
            DatasetInfo(
                id=len(results),
                filename=meta.filename,
                row_count=meta.row_count,
                column_count=meta.column_count,
                uploaded_at=meta.uploaded_at,
            )
        )
    return results


@router.get("/analyst/datasets", response_model=list[DatasetInfo])
def list_datasets():
    if not _UPLOAD_ROOT.exists():
        return []
    out: list[DatasetInfo] = []
    for session_dir in sorted(_UPLOAD_ROOT.iterdir()):
        for csv in sorted(session_dir.glob("*.csv")):
            try:
                df_rows = 0
                df_cols = 0
                try:
                    import pandas as pd

                    df = pd.read_csv(csv, nrows=1)
                    df_cols = len(df.columns)
                    with open(csv, "rb") as f:
                        for _ in f:
                            df_rows += 1
                    df_rows -= 1  # header
                except Exception:  # noqa: BLE001
                    pass
                out.append(
                    DatasetInfo(
                        id=len(out),
                        filename=csv.name,
                        row_count=max(df_rows, 0),
                        column_count=df_cols,
                        uploaded_at=__import__("datetime").datetime.datetime.fromtimestamp(
                            csv.stat().st_mtime
                        ).isoformat(),
                    )
                )
            except Exception:  # noqa: BLE001
                continue
    return out


@router.post("/analyst/query", response_model=QueryResponse)
def query(payload: QueryRequest):
    datasets = [d.filename for d in list_datasets()]
    dataframes: dict[str, Any] = {}
    for name in datasets:
        try:
            import pandas as pd

            path = _UPLOAD_ROOT / "*" / name
            matches = list(_UPLOAD_ROOT.glob(f"*/{name}"))
            if not matches:
                continue
            dataframes[name.replace(".", "_").replace(" ", "_")] = pd.read_csv(
                matches[0]
            )
        except Exception:  # noqa: BLE001
            continue
    state: AgentState = {
        "run_id": __import__("uuid").uuid4().hex,
        "input_text": payload.question,
        "instruction": payload.question,
        "datasets": datasets,
        "_dataframes": dataframes,
        "error": None,
    }
    from src.graph.agent import agentic_ai

    final_state = agentic_ai.invoke(state)
    er = final_state.get("exec_result") or {}
    return QueryResponse(
        output_table=final_state.get("output_table"),
        output_columns=final_state.get("output_columns"),
        output_chart=final_state.get("output_chart"),
        output_text=final_state.get("output_text"),
        generated_code=final_state.get("generated_code"),
        followups=final_state.get("followups"),
        error=final_state.get("error"),
        status=final_state.get("status", "failed"),
    )


@router.get("/analyst/schema/{filename}")
def dataset_schema(filename: str):
    matches = list(_UPLOAD_ROOT.glob(f"*/{filename}"))
    if not matches:
        raise HTTPException(status_code=404, detail="dataset not found")
    import pandas as pd

    df = pd.read_csv(matches[0], nrows=100)
    cols = []
    for c in df.columns:
        cols.append(
            {
                "name": c,
                "dtype": str(df[c].dtype),
                "sample": df[c].dropna().head(3).tolist(),
            }
        )
    return {"filename": filename, "columns": cols, "row_count": len(df)}
