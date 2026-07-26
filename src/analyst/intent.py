"""Intent classification: CSV vs future DB mode."""
from __future__ import annotations

import re


def classify_intent(text: str, filenames: list[str]) -> str:
 lowered = (text or "").lower()
 ascii_text = lowered.encode("ascii", "ignore").decode("ascii")
 if any(k in lowered for k in ["schema", "describe", "column", "col", "head", "sample",
     "scheme", "vyavastha", "kya hai", "batao", "bata do", "sankhya", "data kya",
     "column kya", "column batao", "structure", "smriti"]):
  return "schema"
 if any(k in lowered for k in ["plot", "chart", "graph", "visual", "trend", "histogram", "bar", "line",
     "dikhao", "dikha do", "visualize", "chhape", "chhape chart", "graph banana",
     "chart banana", "trend dekh", "plot banana", "graphik"]):
  return "viz"
 # Hindi generic query cues keep default dataset path
 if re.search(r"[\u0900-\u097F]+", lowered):
  return "query"
 return "query"
