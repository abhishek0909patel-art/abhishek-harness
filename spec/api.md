# API — UP Police Data Analyst

All endpoints are prefixed with `/api/v1`. Auth is a stub in Phase 1–3 (`X-Officer-Id` header); Phase 4 adds proper token auth.

## Datasets

- `POST /api/v1/datasets/upload` — multipart form, field name `files[]` (one or more CSVs). Response: list of persisted datasets with id + schema summary. Rejects files > 50 MB or > 5 M rows per `config.yaml`. Stored under `./data/uploads/<session_id>/`.
- `GET /api/v1/datasets` — list datasets for the current session/officer. Response: id, filename, row_count, column_count, uploaded_at.
- `GET /api/v1/datasets/{dataset_id}/schema` — full column-level metadata (dtype, sample values, description).

## Query

- `POST /api/v1/query` — body: `{"question": str, "dataset_ids": list[int] | null}`. Runs the full graph: classify_intent → retrieve_schema → generate_code → sandbox_execute → verify_output. Response: `output_table`, `output_columns`, `output_chart` (Plotly spec), `output_text`, `generated_code`, `followups`, `audit`, `error`. Maximum execution timeout 30 s.
- `POST /api/v1/query/rerun` — body: `{"generated_code": str, "dataset_ids": list[int] | null}`. Re-runs the supplied code in the sandbox (skips LLM call). Response: same shape as `/query`.
- `GET /api/v1/query/history` — list recent audit events for the current officer. Query params: `limit` (default 50), `offset` (default 0).

## Bookmarks

- `POST /api/v1/bookmarks` — body: `{"name": str, "question": str, "dataset_ids": list[int]}`. Response: bookmark id + saved_at.
- `GET /api/v1/bookmarks` — list bookmarks for the current officer.
- `DELETE /api/v1/bookmarks/{bookmark_id}` — revoke a bookmark.
- `POST /api/v1/bookmarks/{bookmark_id}/share` — body: `{"expires_hours": int | null}`. Response: share token. Anyone with the token can load the bookmark (read-only).

## Audit

- `GET /api/v1/audit` — query params: `officer`, `source`, `start`, `end`, `limit`, `offset`. Admin-only after Phase 4.

## Database

- `POST /api/v1/db/connect` — body: `{"dsn_name": str}`. Validates the connection and warms the schema cache. Response: `{"connected": true, "tables": [...]}`. Credentials come from `.env`; officer never types them in UI.
- `GET /api/v1/db/schema` — list tables + columns for the active DSN, with cache status (fresh / stale / missing).
- `POST /api/v1/db/schema/refresh` — invalidate cache for the active DSN and re-fetch `INFORMATION_SCHEMA`.

## Error Shape

All errors return `{"error": str, "detail": str | null}` with the appropriate HTTP status (400 for bad input, 401 for missing/invalid officer header, 422 for sandbox execution failure, 500 for server faults).
