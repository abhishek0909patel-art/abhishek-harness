"""Graph nodes — CAPABILITY SLOT: CSV Analyst (replaces transform_text).

Baseline nodes (transform_text, handle_error, finalize) are preserved so
existing imports and tests keep working; the graph assembly switches the
entry point to csv_analyst (see src/graph/agent.py).
"""
from __future__ import annotations

import datetime
import logging
from typing import Any

from src.analyst.intent import classify_intent
from src.analyst.metadata_engine import DatasetMeta, load_csv, schema_block
from src.analyst.sandbox import SandboxResult, run_sandbox
from src.analyst.schema_retriever import retrieve_schema
from src.graph.state import AgentState
from src.llm.providers.base import LLMError

log = logging.getLogger(__name__)

_MAX_RETRIES = 2


def csv_analyst(state: AgentState) -> AgentState: # entry point for Phase 1
 datasets = state.get("datasets") or []
 text = state.get("input_text") or state.get("instruction") or ""
 intent = classify_intent(
  text,
  [d.get("filename") if isinstance(d, dict) else d for d in datasets],
 )
 state["source"] = intent
 state["retries"] = 0
 state["schema_block"] = retrieve_schema(_first_dataset_meta(datasets), text) if datasets else ""
 return generate_code(state)


def _first_dataset_meta(datasets: list[Any]) -> DatasetMeta:
 d = datasets[0] if datasets else {}
 if isinstance(d, dict):
  return DatasetMeta(
   session_id=d.get("session_id", ""),
   filename=str(d.get("filename") or d.get("name") or "unknown"),
   sha256=d.get("sha256", ""),
   row_count=int((d.get("row_count") or d.get("rowCount") or 0)),
   column_count=int((d.get("column_count") or d.get("columnCount") or 0)),
   columns=[],
   size_bytes=int(d.get("size_bytes") or d.get("sizeBytes") or 0),
   path=d.get("path", ""),
   uploaded_at=d.get("uploaded_at", ""),
  )
 if isinstance(d, DatasetMeta):
  return d
 return DatasetMeta(
  session_id=getattr(d, "session_id", ""),
  filename=str(getattr(d, "filename", "unknown")),
  sha256=getattr(d, "sha256", ""),
  row_count=int(getattr(d, "row_count", 0)),
  column_count=int(getattr(d, "column_count", 0)),
  columns=getattr(d, "columns", []) or [],
  size_bytes=int(getattr(d, "size_bytes", 0)),
  path=getattr(d, "path", ""),
  uploaded_at=getattr(d, "uploaded_at", ""),
 )


def generate_code(state: AgentState) -> AgentState:
 from src.config.settings import get_settings
 s = get_settings()
 if s.resolve_provider() == "stub":
  state["error"] = (
   "No LLM API key configured. Set exactly one of "
   "AGENT_ANTHROPIC_API_KEY, AGENT_GEMINI_API_KEY, or "
   "AGENT_OPENROUTER_API_KEY in .env (see .env.example)."
  )
  return handle_error(state)
 existing = state.get("generated_code")
 if existing:
  return _sanitize_and_execute(state, existing)
 code = deterministic_local_code(state)
 return _sanitize_and_execute(state, code)


def deterministic_local_code(state: AgentState) -> str:
 question = (state.get("instruction") or state.get("input_text") or "").lower()
 dataframes: dict[str, Any] = state.get("_dataframes") or {}
 keys = list(dataframes.keys())
 df_name = keys[0] if keys else "result"
 df = dataframes.get(df_name)
 if df is None:
  return 'result = "no dataframe loaded"'
 q = question
 if "describe" in q:
  return f"result = {df_name}.describe()"
 if "value_counts" in q or "count" in q:
  return f"result = {df_name}.value_counts().reset_index()"
 if "groupby" in q or "group by" in q or "per " in q or "by " in q:
  return f"result = {df_name}.groupby({df_name}.columns[0]).size().reset_index(name='count')"
 if "head" in q or "sample" in q:
  n = 20 if "all" not in q else 5000
  return f"result = {df_name}.head({n})"
 if "histogram" in q or "plot" in q or "chart" in q or "graph" in q or "visual" in q:
  col = f"{df_name}.columns[0]"
  return f"result = {df_name}.head(200)\nfig = pl.histogram({df_name}, x={col})"
 if "trend" in q or "time" in q or "over time" in q:
  candidates = ["date", "time", "timestamp", "day", "month", "year"]
  cols = getattr(df, "columns", [])
  time_col = next((c for c in cols if any(k in str(c).lower() for k in candidates)), None)
  if time_col:
   return f"result = {df_name}.groupby('{time_col}').size().reset_index(name='count')"
  return f"result = {df_name}.groupby({df_name}.columns[0]).size().reset_index(name='count')"
 if "sum" in q or "total" in q:
  return f"result = {df_name}.groupby({df_name}.columns[0])[{df_name}.columns[-1]].sum().reset_index()"
 if "districts.csv" in q or "district" in q or "list" in q or "show" in q or "display" in q:
  n = 5000 if "all" in q else 20
  return f"result = {df_name}.head({n})"
 return f"result = {df_name}.head(20)\nfig = pl.histogram({df_name}, x={df_name}.columns[0])"


def _sanitize_and_execute(state: AgentState, code: str) -> AgentState:
 state["generated_code"] = code
 dataframes: dict[str, Any] = state.get("_dataframes") or {}
 sandbox: SandboxResult = run_sandbox(code, dataframes)
 state["exec_result"] = {
  "status": "ok" if sandbox.ok else "error",
  "dataframe": sandbox.dataframe,
  "columns": sandbox.columns,
  "chart_spec": sandbox.chart_spec,
  "text": sandbox.text,
  "error": sandbox.error,
 }
 if sandbox.ok:
  state["output_table"] = sandbox.dataframe
  state["output_columns"] = sandbox.columns
  state["output_chart"] = sandbox.chart_spec
  state["output_text"] = sandbox.text
  state["followups"] = _suggest_followups(sandbox)
  return finalize(state)
 retries = (state.get("retries") or 0) + 1
 state["retries"] = retries
 if retries <= _MAX_RETRIES:
  return self_fix(state)
 return handle_error(state)


def self_fix(state: AgentState) -> AgentState:
 if not state.get("generated_code"):
  return _sanitize_and_execute(state, deterministic_local_code(state))
 try:
  code = deterministic_local_code(state)
 except Exception:
  code = "result = df.head(20)"
 return _sanitize_and_execute(state, code)


def _suggest_followups(sandbox: SandboxResult) -> list[str]:
 cols = sandbox.columns or []
 out: list[str] = []
 if len(cols) >= 2:
  out.append(f"group by {cols[0]} and sum {cols[-1]}")
 if any(str(c).endswith(("date", "time", "timestamp")) for c in cols):
  out.append("trend over time")
 out.append("show top 10 rows")
 return out[:3]


def handle_error(state: AgentState) -> AgentState:
 err = state.get("error") or (state.get("exec_result") or {}).get("error") or "unknown error"
 state["error"] = err
 state["status"] = "failed"
 state["audit"] = {
  "query": state.get("instruction"),
  "timestamp": datetime.datetime.now().isoformat(),
  "officer": state.get("run_id"),
  "result_hash": "",
  "source": state.get("source"),
  "status": "failed",
 }
 return state


def finalize(state: AgentState) -> AgentState:
 state["status"] = "completed"
 state.setdefault("error", None)
 state["audit"] = state.get("audit") or {
  "query": state.get("instruction"),
  "timestamp": datetime.datetime.now().isoformat(),
  "officer": state.get("run_id"),
  "result_hash": "",
  "source": state.get("source"),
  "status": "completed",
 }
 return state


# Baseline surface (kept for compatibility)
def transform_text(state: AgentState) -> AgentState: # noqa: D401 — baseline
 try:
  from src.llm.client import LLMClient, load_prompt

  client = LLMClient()
  system = load_prompt("transform")
  user = (
   f"INSTRUCTION:\n{state['instruction']}\n\n"
   f"TEXT:\n{state['input_text']}"
  )
  output = client.complete(system, user, max_tokens=2048)
  return {
   "output_text": output,
   "provider": client.provider_name,
   "model": client.model,
   "error": None,
  }
 except LLMError as exc:
  return {"error": str(exc)}
