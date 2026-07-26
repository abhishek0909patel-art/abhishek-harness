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


def csv_analyst(state: AgentState) -> AgentState:  # entry point for Phase 1
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
 existing = state.get("generated_code")
 if existing:
  return _sanitize_and_execute(state, existing)
 from src.config.settings import get_settings

 s = get_settings()
 if s.resolve_provider() == "stub" and not state.get("_dataframes"):
  state["error"] = (
   "No LLM API key configured. Set exactly one of "
   "AGENT_ANTHROPIC_API_KEY, AGENT_GEMINI_API_KEY, or "
   "AGENT_OPENROUTER_API_KEY in .env (see .env.example)."
  )
  return handle_error(state)
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

 cols = getattr(df, "columns", []) or []
 first = cols[0] if cols else None
 last = cols[-1] if cols else None
 numeric_cols = [c for c in cols if str(df[c].dtype).startswith(("int", "float"))]

 q = question
 if any(k in q for k in ["describe", "summary", "overview"]):
  return f"result = {df_name}.describe()"
 if any(k in q for k in ["missing", "null", "na", "empty", "blank"]):
  return f"result = {df_name}.isna().sum().reset_index()\nresult.columns = ['column', 'missing_count']\nresult = result[result['missing_count'] > 0]"
 if any(k in q for k in ["duplicate", "duplicat", "repeat", "doubl"]):
  return f"result = {df_name}[{df_name}.duplicated(keep=False)]"
 if any(k in q for k in ["correlation", "correlat", "relation", "matrix"]):
  if len(numeric_cols) >= 2:
   return f"result = {df_name}[{list(numeric_cols)}].corr()"
  return f"result = {df_name}.corr(numeric_only=True)"
 if any(k in q for k in ["unique", "distinct", "unik"]):
  if first is not None:
   return f"result = pd.DataFrame({{'{first}': {df_name}['{first}'].unique()}})"
  return f"result = pd.DataFrame({{'unique_count': {df_name}.nunique().values}}, index={df_name}.nunique().index)"
 if any(k in q for k in ["histogram", "hist", "distribution", "distribut"]):
  if first is not None:
   col = first
   return f"result = {df_name}.head(500)\nfig = pl.histogram({df_name}, x='{col}', nbins=20)"
 if any(k in q for k in ["plot", "chart", "graph", "visual", "bar", "line", "scatter"]):
  x = first if first is not None else "index"
  y = numeric_cols[0] if numeric_cols else None
  if y:
   return f"result = {df_name}.head(200)\nfig = pl.bar({df_name}, x='{x}', y='{y}')"
  return f"result = {df_name}.head(200)\nfig = pl.histogram({df_name}, x='{x}', nbins=20)"
 if any(k in q for k in ["trend", "time", "over time", "time series", "samay"]):
  candidates = ["date", "time", "timestamp", "day", "month", "year"]
  time_col = next((c for c in cols if any(k in str(c).lower() for k in candidates)), None)
  if time_col and numeric_cols:
   return f"result = {df_name}.groupby('{time_col}')[{numeric_cols[0]}].mean().reset_index()\nfig = pl.line(result, x='{time_col}', y='{numeric_cols[0]}')"
  if time_col:
   return f"result = {df_name}.groupby('{time_col}').size().reset_index(name='count')"
 if any(k in q for k in ["average", "avg", "mean", "median", "mode"]):
  if numeric_cols:
   return f"result = {df_name}[{numeric_cols}].mean().reset_index()"
  return f"result = {df_name}.mean(numeric_only=True).reset_index()"
 if any(k in q for k in ["sum", "total", "kul", "joda"]):
  if first and last and str(df[last].dtype).startswith(("int", "float")):
   return f"result = {df_name}.groupby('{first}')['{last}'].sum().reset_index()"
  if last and str(df[last].dtype).startswith(("int", "float")):
   return f"result = pd.DataFrame({{'{last}': [{df_name}['{last}'].sum()]}})"
  if numeric_cols:
   return f"result = {df_name}[{numeric_cols}].sum().reset_index()"
  return f"result = {df_name}.sum(numeric_only=True).reset_index()"
 if any(k in q for k in ["min", "minimum", "lowest", "sabse kam"]):
  if numeric_cols:
   return f"result = {df_name}[{numeric_cols}].min().reset_index()"
  return f"result = {df_name}.min(numeric_only=True).reset_index()"
 if any(k in q for k in ["max", "maximum", "highest", "sabse zyada"]):
  if numeric_cols:
   return f"result = {df_name}[{numeric_cols}].max().reset_index()"
  return f"result = {df_name}.max(numeric_only=True).reset_index()"
 if any(k in q for k in ["count", "how many", "frequency", "kitna", "kitne"]):
  if len(cols) >= 2:
   return f"result = {df_name}.groupby('{first}').size().reset_index(name='count')"
  return f"result = pd.DataFrame({{'row_count': [len({df_name})]}})"
 if any(k in q for k in ["top", "highest", "best", "sabse upar", "sabse zyada"]):
  if numeric_cols and first:
   return f"result = {df_name}.groupby('{first}')['{numeric_cols[0]}'].sum().reset_index().sort_values('{numeric_cols[0]}', ascending=False).head(20)"
  if first:
   return f"result = {df_name}.groupby('{first}').size().reset_index(name='count').sort_values('count', ascending=False).head(20)"
 if any(k in q for k in ["bottom", "lowest", "worst", "sabse nich"]):
  if numeric_cols and first:
   return f"result = {df_name}.groupby('{first}')['{numeric_cols[0]}'].sum().reset_index().sort_values('{numeric_cols[0]}', ascending=True).head(20)"
  if first:
   return f"result = {df_name}.groupby('{first}').size().reset_index(name='count').sort_values('count', ascending=True).head(20)"
 if any(k in q for k in ["percent", "ratio", "proportion", "pratishat", "hissa"]):
  if len(cols) >= 2 and numeric_cols:
   return f"result = {df_name}.groupby('{first}')['{numeric_cols[0]}'].sum().reset_index()\nresult['percentage'] = result['{numeric_cols[0]}'] / result['{numeric_cols[0]}'].sum() * 100"
 if any(k in q for k in ["group", "by ", "ke hisab", "ke anusar", "category", "category-wise"]):
  if len(cols) >= 2:
   return f"result = {df_name}.groupby('{first}').size().reset_index(name='count')"
 if any(k in q for k in ["value_counts", "value count", "values"]):
  return f"result = {df_name}.value_counts().reset_index()"
 if any(k in q for k in ["head", "sample", "preview", "glimpse", "top 5", "top 10"]):
  return f"result = {df_name}.head(20)"
 if any(k in q for k in ["all", "full", "complete", "entire", "sab", "poora"]):
  return f"result = {df_name}"
 return f"result = {df_name}"


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
def transform_text(state: AgentState) -> AgentState:  # noqa: D401 — baseline
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
