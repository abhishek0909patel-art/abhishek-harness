"""Keyword schema retrieval for the loaded CSV datasets."""
from __future__ import annotations

from src.analyst.metadata_engine import DatasetMeta, schema_block


def retrieve_schema(meta: DatasetMeta, query: str, max_columns: int = 5) -> str:
    tokens = [t.lower() for t in query.split() if len(t) > 2]
    ranked = sorted(
        meta.columns,
        key=lambda c: sum(t in c.name.lower() or t in (c.description or "").lower() for t in tokens),
        reverse=True,
    )
    top = ranked[:max_columns]
    if not top:
        return schema_block(meta, max_cols=max_columns)
    lines = [f"Table: {meta.filename} ({meta.row_count} rows)"]
    for c in top:
        samples = ", ".join(repr(v) for v in (c.sample_values or [])[:2])
        lines.append(f"- {c.name} ({c.dtype}) samples: [{samples}]")
    return "\n".join(lines)
