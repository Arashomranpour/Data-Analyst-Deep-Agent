---
paths:
  - "analyst/data/**"
  - "analyst/tools/**"
---
# Data store and tools
- `DataStore` is read-only SQLite via an authorizer, with a `max_rows` cap and `QUERY_TIMEOUT_S` limit.
  Do not add write paths; loading goes through `load_dataframe` only.
- Tools: `list_tables`, `describe_table`, `run_sql`, `make_chart` (built in `build_toolkit`). `run_sql` must go
  through the SQL guard and feed results into `Evidence` (used by GroundedNumbers) and the tool-output guard.
- `make_chart` takes structured specs only, no code execution. Artifacts (charts, `/report.md`) live in `Artifacts`.
- `sample.py` is deliberately booby-trapped (PII, duplicates, outlier, injection in `notes`). Tests depend on it;
  changing it means updating the red-team tests.
