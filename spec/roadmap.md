# Roadmap — UP Police Data Analyst

> Spec-driven harness build. Every phase is one user-testable increment behind a human gate.

Assumed: Ollama is the default local LLM for Phase 1 (Anthropic/Gemini/OpenRouter wiring comes from the harness provider layer and can be swapped via `.env`). Assumed: "Station officer" is the primary persona; role-based row masking is implemented as a SQL/pandas filter, not a full identity provider (Phase 4 adds auth). Assumed: chart library is Plotly for interactive exploration in the UI, with matplotlib as a silent fallback. Assumed: audit trail writes to SQLite in Phase 1; Phase 4 migrates audit writes to MS SQL if connected.

---

## What This Agent Does

A natural-language data-analyst agent for station-level officers of the UP Police. Officers upload CSV exports (crime, FIR, arrest logs), ask questions in plain language, and receive formatted tables, interactive Plotly charts, and suggested follow-ups. Generated pandas code is shown in the UI for transparency and lets the officer edit and re-run it. The same capability slot is architected to extend to live MS SQL database queries with schema caching, query-result caching, and role-based row masking — keeping DB load low and latency under 1 s for 10–50 M row tables.

## Who Uses It

Station-level officers running ongoing investigations. They load one or more CSVs, ask many related questions in a single session, and rely on an in-session audit trail of every query, timestamp, and result.

## Core Problem Being Solved

Today, officers export station data to CSV and manually open it in Excel or ask a data analyst — slow, error-prone, no self-service, no audit trail. This agent removes the analyst bottleneck: upload, ask, get a chart, drill in, save the query, and move on.

## Success Criteria

- [ ] An officer can upload two or more CSV files and get a schema summary in under 10 s.
- [ ] A natural-language question returns a table and chart in under 5 s (single CSV, < 1 M rows).
- [ ] Generated pandas code is visible, editable, and re-runnable inside the chat.
- [ ] Every query is logged with officer id (user label), timestamp, and result hash.
- [ ] MS SQL extension loads table metadata with ≤ 30 s cold-start, reuses cache thereafter.
- [ ] Cross-district aggregates over 10 M rows complete in under 1 s 9x times out of 10.

## Out of Scope

- PDF/scanned record ingestion (OCR is not in scope).
- Real-time streaming from patrol apps.
- Multi-officer collaboration in the same session.
- Automatic schema fusion / auto-join across unrelated CSVs (join is always explicit).
- Voice/translation layer.

## Key Constraints

- All processing is local-first; data never leaves the premises.
- Minimal external spend: prefer Ollama; Anthropic/Gemini/OpenRouter used only if configured.
- Read-only MS SQL connection — the agent never issues INSERT/UPDATE/DELETE.
- Role-based row masking applied as a filter at the pandas/SQL layer.
- Phase 1 must work with zero MS SQL configuration.

---

## Phases

### Phase 1 — CSV Analyst Core

- **Goal:** The smallest user-testable win — one officer uploads two CSVs, asks a question, sees a table + chart + generated code, and can re-run edited code.
- **Independent slices (parallel build units):**
  - `slice-a` (backend) — CSV metadata engine, intent classifier, schema retrieval by keyword match, LLM code generation (Ollama + heuristic fallback), sandboxed execution, result shaping; deps: none.
  - `slice-b` (frontend) — Streamlit UI: sidebar CSV uploader, schema summary, main chat area, collapsible generated-code panel (read/edit/rerun), results area (table + Plotly), audit log sidebar; deps: none.
- **Key surfaces/files:**
  - Backend: replace `src/graph/nodes.py` `csv_analyst` node, extend `src/graph/state.py`, add `src/analyst/` (metadata_engine, sandbox, intent, schema_retriever), extend `src/prompts/csv-analyst.md`.
  - Frontend: new `frontend/analyst/` served under `/app/analyst` (streamlit or FastAPI template).
- **Gate command:** `uv run pytest tests/integration/test_phase1_csv.py -q`
- **How the user tests it:** Open `/app/analyst`, click "Choose Files" and upload two CSVs, view the auto-inferred schema, type "How many cases per district?", see a table + a bar chart plus collapsible generated pandas code, edit a column name in the code, click "Re-run", see the updated result.

### Phase 2 — Bookmarks, Session Memory & Follow-up Suggestions

- **Goal:** Officers can bookmark/share queries, see suggested follow-ups, and return to an ongoing session with their prior queries intact.
- **Independent slices (parallel build units):**
  - `slice-a` (backend) — bookmarks model + API (create/list/delete/share), in-session conversation history, follow-up suggestion generator; deps: Phase 1 backend.
  - `slice-b` (frontend) — bookmark buttons, session history sidebar, follow-up chip list; deps: Phase 1 frontend.
- **Key surfaces/files:**
  - Backend: `src/domain/bookmark.py`, `src/api/bookmarks.py`, extend `src/graph/state.py` with `suggested_followups`.
  - Frontend: `frontend/analyst/bookmarks.js`, chat-history widget.
- **Gate command:** `uv run pytest tests/integration/test_phase2_bookmarks.py -q`
- **How the user tests it:** Upload CSVs, ask one question, click "Bookmark", refresh the page, see the query still listed; click a suggested follow-up chip and confirm it runs.

### Phase 3 — MS SQL Connector & Caching Layer

- **Goal:** Same chat workflow against a live MS SQL database, with schema caching and query-result caching keeping latency low and DB load minimal.
- **Independent slices (parallel build units):**
  - `slice-a` (backend) — `db_connector.py` (SQLAlchemy + pyodbc), schema cache (Redis or SQLite fallback), query cache (md5 + TTL), load-optimized preview (LIMIT/OFFSET), aggregate pre-computation hooks; deps: none.
  - `slice-b` (backend/frontend) — intent classifier now routes DB vs CSV; DB schema surfaced in chat; same code-gen runner generates SQLAlchemy-flavoured code for MS SQL in addition to pandas; deps: Phase 1 slices.
- **Key surfaces/files:**
  - Backend: `src/analyst/db_connector.py`, `src/analyst/cache_layer.py`, extend intent + code-gen prompts.
  - Frontend: DB-connection form (host, DSN, credentials stored in `.env` once confirmed), schema-browser panel.
- **Gate command:** `uv run pytest tests/integration/test_phase3_mssql.py -q`
- **How the user tests it:** Configure `.env` with MS SQL DSN, open `/app/analyst`, select "MS SQL" as source, browse cached schema, run an aggregate query, verify the result returned in under 1 s and that a second identical query hits the cache.

### Phase 4 — Auth, Audit Hardening & Role Masking

- **Goal:** Production reliability — role-based row masking, signed audit receipts, per-officer cost dashboard, graceful LLM fallback.
- **Independent slices (parallel build units):**
  - `slice-a` (backend) — row-masking middleware (SQL WHERE + pandas `.query()`), signed audit receipts (HMAC), cost-dashboard aggregator; deps: Phase 2/3.
  - `slice-b` (backend/frontend) — authN stub (station/badge id => role), error-route UX for LLM downtime (heuristic fallback shows, "running offline mode"); deps: Phase 2/3.
- **Key surfaces/files:**
  - Backend: `src/analyst/mask.py`, `src/analyst/audit.py`, test fixtures for role fixtures.
  - Frontend: officer-id prompt, role badge, cost widget, offline-mode banner.
- **Gate command:** `uv run pytest tests/integration/test_phase4_hardening.py -q`
- **How the user tests it:** Log in as officer rank "inspector" (masked role), run a query that a "constable" cannot see; verify the masked rows are absent; confirm an audit receipt is written with a valid signature; confirm the offline-mode banner appears when the LLM provider is unreachable.
