# Data — UP Police Data Analyst

## CSV Metadata Schema

Table: `csv_datasets`
- `id` INTEGER PRIMARY KEY
- `session_id` TEXT NOT NULL
- `officer` TEXT NOT NULL
- `filename` TEXT NOT NULL
- `sha256` TEXT NOT NULL
- `row_count` INTEGER NOT NULL
- `column_count` INTEGER NOT NULL
- `columns_json` TEXT NOT NULL — JSON list of `{name, dtype, sample_values, description}`
- `size_bytes` INTEGER NOT NULL
- `uploaded_at` TEXT NOT NULL (ISO-8601)
- UNIQUE (`session_id`, `filename`)

Table: `csv_datasets` row:
```json
{
  "filename": "fir_june_2026.csv",
  "dtypes": {
    "station": "string",
    "date": "date",
    "section": "string",
    "status": "category"
  },
  "sample_rows": [
    {"station": "Lucknow", "date": "2026-06-01", "section": "379 IPC", "status": "Under investigation"}
  ]
}
```

## Audit Log Schema

Table: `audit_log`
- `id` INTEGER PRIMARY KEY
- `timestamp` TEXT NOT NULL (ISO-8601)
- `officer` TEXT NOT NULL
- `source` TEXT NOT NULL — "csv" or "db"
- `query` TEXT NOT NULL
- `status` TEXT NOT NULL — "completed" | "failed" | "fallback"
- `result_hash` TEXT NOT NULL — md5 of the rendered result (table rows + narrative)
- `result_summary` TEXT — first 2 000 chars of `output_text` or error message
- `metadata_json` TEXT — `{dataset_names, row_count, column_names, generated_code_hash}`
- `signature` TEXT | NULL — HMAC-SHA256 signed receipt (Phase 4; NULL before hardening)

Indexes: (`officer`, `timestamp DESC`), (`source`, `timestamp DESC`).

## MS SQL Schema-Cache Schema

Table: `db_schema_cache`
- `id` INTEGER PRIMARY KEY
- `dsn_name` TEXT NOT NULL
- `table_name` TEXT NOT NULL
- `column_name` TEXT NOT NULL
- `data_type` TEXT NOT NULL
- `is_nullable` INTEGER NOT NULL
- `sample_values_json` TEXT — optional cached examples
- `row_count_estimate` INTEGER | NULL
- `cached_at` TEXT NOT NULL (ISO-8601)
- `expires_at` TEXT NOT NULL (ISO-8601)
- UNIQUE (`dsn_name`, `table_name`, `column_name`)

Table: `db_query_cache`
- `id` INTEGER PRIMARY KEY
- `dsn_name` TEXT NOT NULL
- `query_hash` TEXT NOT NULL — md5 of the normalised query string
- `query_text` TEXT NOT NULL
- `result_json` TEXT NOT NULL — serialised DataFrame (rows + columns) or SQL scalar
- `created_at` TEXT NOT NULL
- `expires_at` TEXT NOT NULL
- UNIQUE (`dsn_name`, `query_hash`)

TTL is configurable in `config.yaml` (`db.query_cache_ttl_seconds`, default 300).

## Row-Masking Rules

Row masking is declared as a Predicate object attached to a dataset or DB table:

```python
@dataclass
class MaskRule:
    source: str  # "csv" | "db"
    dataset: str
    column: str
    op: str  # "eq" | "in" | "range"
    values: list | tuple  # allowed values or (low, high) for range
    role_required: str | None  # None means all roles see the rule; else only this role sees unrestricted
```

- CSV path: after loading the DataFrame, every `MaskRule` with `source == "csv"` is applied as `df = df.query(mask_expression)` before the user's code runs.
- DB path: every `MaskRule` with `source == "db"` is appended as a `WHERE` clause to the generated SQL.
- If `role_required` is set and the current officer's role does not match, the restricted rows are silently excluded.
- Rules are loaded from a JSON config administered out-of-band by the station superintendent; they are never editable by officers through the UI.
- Audit event records which rules were applied (masked column names only, not values) in `metadata_json.masking`.

## Upload Configuration Defaults

- Max file size: 50 MB
- Max rows per file: 5 000 000
- Allowed encodings: UTF-8, Latin-1 (auto-detected)
- Staging directory: `./data/uploads/<session_id>/` (never hardcoded absolute paths).
