# Architecture — UP Police Data Analyst

## Component Diagram (textual)

```
[Browser / Station PC]
       |
       v
[Frontend surface — static assets under frontend/analyst/; Streamlit or FastAPI+HTMX]
       |
       v
[API Gateway — FastAPI (harness src/api/)]
   |               |
   |               v
   |         [Auth / Role layer] (Phase 4)
   |               |
   v               v
[Agent Graph — LangGraph] → [Audit writer — SQLite today; MS SQL later]
       |
       +-- classify_intent (CSV vs DB)
       +-- retrieve_schema (keyword match / DB info_schema)
       +-- generate_code (one LLM call — pandas OR SQLAlchemy)
       +-- sandbox_execute (restricted namespace, pandas/SQLAlchemy only)
       +-- verify_output (type/size/error check)
       +-- self_fix loop (up to N retries — simpler fallback prompt)
       +-- handle_error / finalize
       |
       v
[Data plane]
  - CSV engine  → local filesystem (upload dir) + pandas DataFrame cache
  - DB engine   → SQLAlchemy + pyodbc → MS SQL instance
  - Cache layer → in-memory LRU + Redis (or diskcache/SQLite fallback)
       |
       v
[LLM provider layer — reuses harness src/llm/providers/]
  Ollama (llama3/mistral) / Anthropic / Gemini / OpenRouter
```

## Data Flow

1. Officer uploads one or more CSVs via the sidebar. Each file is stored under a session-specific upload directory; metadata (sha256, columns, dtypes, row count, sample rows, upload timestamp) is persisted to SQLite.
2. Officer submits a natural-language question in the chat.
3. The graph calls `classify_intent`. If a DB source is configured and selected, the path switches to the MS SQL branch; otherwise the CSV branch runs.
4. `retrieve_schema` fetches the relevant table/column list by keyword match against the persisted metadata and surfaces a compact schema block in the prompt.
5. `generate_code` calls the LLM once to produce a full pandas (or SQLAlchemy) snippet. It is checked for banned calls (network, system, file write outside the sandbox) before execution.
6. `sandbox_execute` runs the snippet in a restricted namespace containing only `pd`, `np`, `pl` (Plotly express), `matplotlib.pyplot`, and the session DataFrames. Outputs are captured as a tuple of `(df_or_series, figure_or_none, text_or_none)`.
7. `verify_output` classifies the result: rich result → finalize; code error / empty → `self_fix` (up to two retries with a degraded prompt); unrecoverable → `handle_error` and surface the code for manual edit.
8. Results stream back to the frontend as a rendered table plus Plotly figure. Suggested follow-ups are appended to the chat as selectable chips.

## Chosen Stack

**## Stack**

- Language/runtime: Python 3.11
- Agent framework: LangGraph (harness baseline `src/graph/` kept intact)
- API server: FastAPI (harness baseline)
- Primary UI: Streamlit standalone service at `/app/analyst` (fastest path to rich tables + Plotly); FastAPI serves static assets and proxies auth state. Alternative: FastAPI + HTMX, deferred to Phase 2 if the Streamlit path proves limiting.
- Data local: SQLite for metadata + audit + cache fallback (harness baseline `src/db/` reused)
- Data remote: MS SQL via SQLAlchemy + pyodbc (optional, isolated behind `src/analyst/db_connector.py`)
- LLM: Ollama (llama3.2 / mistral) preferred for cost/latency; provider-agnostic harness layer lets Anthropic/Gemini/OpenRouter replace it via `.env`.
- Caching: `cachetools.LRUCache` in-memory, `diskcache` folder on disk, optional Redis for schema + query caching.
- Observability: structured log lines per query (harness `src/observability/` reused); audit events written to SQLite.
- Test stack: pytest + httpx for API integration; pandas + plotly smoke tests for the UI path.
