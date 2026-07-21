The previous pandas code failed with the error shown below.
Write a MUCH SIMPLER replacement that cannot raise.

Rules:
- Output ONLY a ```python fence. No commentary before or after.
- Assign ONLY `result = ...` (no `fig`).
- Use only: .head(), .describe(), .value_counts(), .groupby(...).size(),
  .groupby(...).sum(), .groupby(...).mean(), .sort_values(), .reset_index()
- No user-defined functions, no list comprehensions, no apply(), no lambda.
- The DataFrame variables follow the same naming rule as before.

Error from the failed code:
{error}

Original (failing) code:
```python
{bad_code}
```

Question again:
{question}
