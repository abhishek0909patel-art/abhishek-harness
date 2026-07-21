"""Metadata engine for uploaded CSV datasets."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

UPLOAD_ROOT = Path(os.environ.get("UP_ANALYST_UPLOAD_ROOT", "./data/uploads"))


@dataclass
class ColumnMeta:
    name: str
    dtype: str
    sample_values: list[Any] = field(default_factory=list)
    description: str | None = None


@dataclass
class DatasetMeta:
    session_id: str
    filename: str
    sha256: str
    row_count: int
    column_count: int
    columns: list[ColumnMeta]
    size_bytes: int
    path: Path
    uploaded_at: str


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _infer_dtype(series: pd.Series) -> str:
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    unique = series.dropna().unique()
    if len(unique) <= 20 and series.nunique() / max(len(series), 1) < 0.5:
        return "category"
    return "string"


def load_csv(path: Path, session_id: str, max_rows: int = 5_000_000) -> DatasetMeta:
    df = pd.read_csv(path, nrows=max_rows + 1)
    if len(df) > max_rows:
        raise ValueError(
            f"{path.name} has {len(df)} rows; limit is {max_rows}. "
            "Split the file or raise the limit in config."
        )
    cols = []
    for col in df.columns:
        s = df[col]
        meta = ColumnMeta(
            name=str(col),
            dtype=_infer_dtype(s),
            sample_values=s.dropna().head(3).tolist(),
        )
        cols.append(meta)
    meta = DatasetMeta(
        session_id=session_id,
        filename=path.name,
        sha256=_sha256(path),
        row_count=len(df),
        column_count=len(df.columns),
        columns=cols,
        size_bytes=path.stat().st_size,
        path=path,
        uploaded_at=pd.Timestamp.now().isoformat(),
    )
    return meta


def schema_block(meta: DatasetMeta, max_cols: int = 20) -> str:
    lines = [f"Table: {meta.filename} ({meta.row_count} rows)"]
    for c in meta.columns[:max_cols]:
        samples = ", ".join(repr(v) for v in (c.sample_values or [])[:2])
        lines.append(f"- {c.name} ({c.dtype}) samples: [{samples}]")
    if len(meta.columns) > max_cols:
        lines.append(f"... and {len(meta.columns) - max_cols} more columns")
    return "\n".join(lines)
