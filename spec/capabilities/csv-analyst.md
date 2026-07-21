# Capability — CSV Analyst

## What It Does

Replaces the harness baseline's `transform_text` capability with a natural-language data analyst for tabular CSV exports. An officer uploads one or more CSV files, views an inferred schema, asks questions in plain language, and receives a formatted table, an interactive Plotly chart, and a short narrative. The generated pandas code is shown in an editable panel and can be re-run. The agent self-corrects up to two times when code errors occur, then surfaces the code for manual intervention. Suggested follow-up queries are offered after each successful run.

## Inputs

- `instruction`: str — the officer's natural-language question.
- `input_text`: str — chat context history (last N turns) for follow-up resolution.
- `datasets`: list[str] — names of loaded CSV files (set by the upload UI).
- `file_bytes`: bytes — raw CSV content (stored server-side, not sent to the LLM).
- `officer`: str — officer/badge id for the audit log (from the auth stub in Phase 4; empty string in earlier phases).

## Outputs

- `output_table`: list[dict] — rendered rows (≤ 1 000) for the UI table.
- `output_columns`: list[str] — column headers.
- `output_chart`: dict | None — Plotly figure JSON for the chart panel.
- `output_text`: str — narrative summary / aggregate headline.
- `generated_code`: str — pandas snippet, visible and editable in the UI.
- `followups`: list[str] — suggested follow-up questions.
- `audit`: dict — `query`, `timestamp`, `officer`, `result_hash`, `source="csv"`, `status` ("completed" | "failed" | "fallback").
- `error`: str | None — human-readable message on failure.

## External Calls

- LLM (one call per successful generation, one call per self-fix retry): via harness `src/llm/providers/` — Ollama by default, Anthropic / Gemini / OpenRouter via `.env`.
- No third-party APIs. No outbound network from the sandbox. No calls to external analytics services.

## Error Cases

- LLM unreachable: fall back to a heuristic pandas executor that handles a small catalogue of templates (`head`, `describe`, `value_counts`, `groupby sum/count`) without an LLM call. Log `audit.status = "fallback"`.
- Code raises during execution: return to `self_fix` (up to two retries). If still failing, preserve the code for editing and set `error` to the last exception message.
- CSV is too large (> 50 MB or > 5 M rows by default): reject at upload with a clear message. Configurable threshold via `config.yaml`.
- CSV parse error (wrong encoding, malformed): return an error with the offending file name; do not crash the session.
- Empty / opaque question: ask the officer to rephrase (UI hint), no LLM call billed.

## Success Criteria

- Phase 1 gate passes: `uv run pytest tests/integration/test_phase1_csv.py -q` green and the live `/app/analyst` path (upload → question → table + chart) observed by a human tester.
- End-to-end latency P95 under 5 s for a 500 k-row CSV on the reference hardware (station laptop, 16 GB RAM, no GPU).
- The LLM-generated code for the canonical five queries (`head`, `describe`, `value_counts`, `groupby sum`, `filter then aggregate`) executes without self-fix on the first attempt at least 80 % of the time across three CSV fixtures.
- Audit event is written to SQLite for 100 % of completed and failed queries.
- Generated code panel is visible and editable in the UI; edits flow through the same sandbox before the result is accepted.
