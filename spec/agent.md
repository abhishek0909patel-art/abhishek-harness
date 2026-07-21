# Agent — UP Police Data Analyst (LangGraph)

## Graph Topology

```
START
 |
 v
classify_intent
 |
 +-- "csv" ---> retrieve_schema
 |                |
 |                v
 |            generate_code
 |                |
 |                v
 |            sandbox_execute
 |                |
 |          +-----+------+
 |          |             |
 |        OK              ERROR or empty
 |          |             |
 |          v             v
 |      verify_output     self_fix (max 2)
 |          |             |        |
 |          |          retries>0?  no → handle_error
 |          |             |        |
 |          +-------------+        |
 |                    |            |
 |                    v            v
 |                 finalize <-- handle_error
 |                    |
 |                    v
 |                  END
 |
 +-- "db" ---> retrieve_db_schema
 |                |
 |                v
 |            generate_sql_code
 |                |
 |                v
 |            sql_execute
 |                |
 |          +-----+------+
 |          |             |
 |        OK              ERROR
 |          |             |
 |          v             v
 |      verify_output     self_fix (max 2)
 |          |             |        |
 |          |          retries>0?  no → handle_error
 |          |             |        |
 |          +-------------+        |
 |                    |            |
 |                    v            v
 |                 finalize <-- handle_error
 |                    |
 |                    v
 |                  END
 |
 +-- "unknown" --> handle_error
```

## State Schema

The graph reuses `src/graph/state.py` (`AgentState`) and adds the following keys.

- `source`: "csv" | "db" | "unknown"
- `datasets`: list[str] — names of loaded CSVs or connected DB tables
- `schema_block`: str — compact column/type summary for the active source
- `generated_code`: str — pandas or SQLAlchemy snippet produced by the LLM
- `exec_result`: dict — keys `dataframe` (list of rows), `columns`, `chart_spec` (Plotly figure JSON), `text`, `error`
- `retries`: int — current self-fix attempt count (reset to 0 on first entry)
- `followups`: list[str] — suggested next queries
- `output_table`: list[dict] | None — rendered table rows for the UI
- `output_chart`: dict | None — Plotly figure spec
- `output_text`: str | None — narrative summary
- `audit`: dict — `query`, `timestamp`, `officer`, `result_hash`, `source`, `status`

## Nodes

### classify_intent(state) -> partial state

Reads `state["input_text"]` against a short classifier prompt. Writes:
- `source`: "csv" if the user message references the loaded datasets, "db" if the user explicitly mentions the live database, otherwise "unknown".
- Retries: 0.
- Deterministic keyword and regex heuristics run before the LLM call so that a missing Ollama process still routes correctly.

### retrieve_schema(state) -> partial state

Fetches the metadata block for the source selected by `classify_intent`. For CSV: keyword match (`state["input_text"]`) against persisted column names and descriptions in SQLite; returns the top-k (k=5) columns with type + sample values. For DB: queries `INFORMATION_SCHEMA.COLUMNS` (or the cached schema if present) and returns the matching columns. Writes `schema_block`.

### generate_code / generate_sql_code(state) -> partial state

Single LLM call, exactly once unless self_fix reroutes back. Prompt surfaces:
- user question
- `schema_block`
- rules (pandas for CSV path; SQLAlchemy Core or text for DB path; no network/system/file calls; return DataFrame or Series)
- response schema: a single ```python code fence with a leading `result = ...` assignment and optional `fig = ...` for Plotly.

Writes `generated_code`. `retries` unchanged.

### sandbox_execute / sql_execute(state) -> partial state

Runs `generated_code` in a restricted namespace:
- allowed builtins: `abs`, `len`, `round`, `min`, `max`, `sum`, `sorted`, `list`, `dict`, `set`, `tuple`, `range`, `enumerate`, `zip`, `map`, `filter`, `isinstance`, `type`, `str`, `int`, `float`, `bool`, `datetime`.
- imported modules: only `pandas` (as `pd`), `numpy` (as `np`), `plotly.express` (as `pl`), `matplotlib.pyplot` (as `plt`), plus session DataFrames keyed by dataset name.
- Banned tokens: `import` / `from` outside a hardcoded allowlist, `__import__`, `open`, `exec`, `eval`, `compile`, `globals`, `locals`, `getattr`, `setattr`, `delattr`, `os.`, `sys.`, `subprocess`, `socket`, `requests`, `urllib`, `http`, `ftp`, `shutil`, `pathlib`.
- Timeout: 10 s. Memory: bounded by the enclosing process.

DB path uses SQLAlchemy text() with a 30 s query timeout and `LIMIT` enforced automatically for preview; aggregates are allowed.

Writes `exec_result` with one of:
- `{"status": "ok", "dataframe": [...], "columns": [...], "chart_spec": {...} | None, "text": "..."}` — success.
- `{"status": "error", "error": "…"}` — failure.

### verify_output(state) -> partial state

Success criteria:
- CSV path: `dataframe` is non-empty and has ≤ 1 000 rows (auto-truncates with a notice beyond that) AND `error` is absent.
- DB path: `dataframe` is non-empty OR `text` carries a meaningful aggregate result (row count, sum, average).

Writes `output_table`, `output_chart`, `output_text`. If criteria pass: `status = "completed"` and jumps to `finalize`. If fail: increments `retries`; if `retries < max_retries (2)` jumps to `self_fix`; else `handle_error`.

### self_fix(state) -> partial state

Builds a degraded prompt: show the failing code and the error message, instruct the LLM to return a simpler snippet that cannot raise (e.g., `df.describe()`, `df.groupby(...).size()`, or `SELECT COUNT(*) FROM …`). Writes `generated_code` and returns to `sandbox_execute` / `sql_execute`. Loop cap: 2 — after 2 failed retries control passes to `handle_error`.

### handle_error(state) -> partial state

Writes:
- `status`: "failed"
- `error`: human-readable message
- `generated_code`: preserved for UI editing.
Leaves `output_table`, `output_chart`, `output_text` empty. Routes to `finalize` so the UI always returns a final status (never raises through the graph).

### finalize(state) -> partial state

Writes `status`: "completed" | "failed". Commits the audit event to SQLite (non-fatal if the write fails — log only). Returns to END.

## Routing Summary

```
classify_intent
  source == "csv"       -> retrieve_schema
  source == "db"        -> retrieve_db_schema
  source == "unknown"   -> handle_error
retrieve_schema         -> generate_code
retrieve_db_schema      -> generate_sql_code
generate_code           -> sandbox_execute
generate_sql_code       -> sql_execute
sandbox_execute
  exec_result.status == "ok"      -> verify_output
  exec_result.status == "error"   -> self_fix (if retries < 2) else handle_error
sql_execute
  exec_result.status == "ok"      -> verify_output
  exec_result.status == "error"   -> self_fix (if retries < 2) else handle_error
verify_output
  pass                           -> finalize
  fail && retries < 2            -> self_fix
  fail && retries == 2           -> handle_error
self_fix                         -> sandbox_execute / sql_execute
handle_error                     -> finalize
finalize                         -> END
```

## Replaces Baseline

The baseline's `transform_text` node is removed from the graph assembly and replaced by `csv_analyst` (the composite entry point that runs `classify_intent` → … → `finalize`). The API surface `/transform` is remounted to `/query` so existing harness tests for graph compilation keep passing while the new capability ships separately.
