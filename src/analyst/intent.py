"""Intent classification: CSV vs future DB mode."""
from __future__ import annotations

import re

CSV_HINTS = re.compile(
    r"(upload|csv|file|table|dataset|schema|describe|groupby|value_counts|filter|sort)",
    re.I,
)
DB_HINTS = re.compile(
    r"(database|db|sql|server|mssql|query|connection|dsn|live|district|statewide)",
    re.I,
)


def classify_intent(text: str, loaded_datasets: list[str]) -> str:
    has_csv = bool(loaded_datasets)
    csv_score = 0
    db_score = 0
    if has_csv:
        csv_score += len(CSV_HINTS.findall(text)) * 2
    db_score += len(DB_HINTS.findall(text)) * 2
    if not has_csv and db_score == 0:
        return "unknown"
    if has_csv and csv_score >= db_score:
        return "csv"
    if db_score > 0:
        return "db"
    return "unknown"
