"""Intent classification: CSV vs future DB mode."""
from __future__ import annotations

import re


def classify_intent(text: str, filenames: list[str]) -> str:
 lowered = (text or "").lower()
 if any(k in lowered for k in ["schema", "describe", "column", "col", "head", "sample"]):
  return "schema"
 if any(k in lowered for k in ["plot", "chart", "graph", "visual", "trend", "histogram", "bar", "line", "graph"]):
  return "viz"
 return "query"
