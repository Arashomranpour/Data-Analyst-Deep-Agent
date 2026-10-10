"""In-memory SQLite database holding the user's tables.

Safety is layered: (1) the Guardrails AI SQL validator checks every query before it gets
here, and (2) this module enforces read-only access *itself* with SQLite's authorizer, a
row cap and a wall-clock timeout, so a bug in the first layer cannot damage the data.
"""

import re
import sqlite3
import threading
import time
from dataclasses import dataclass

import pandas as pd

_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
}
_BLOCKED_FUNCTIONS = {"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer"}


class QueryError(Exception):
    """A query failed (syntax error, timeout, denied operation...)."""


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    truncated: bool

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=self.columns)


def _authorizer(action, arg1, arg2, db_name, source):
    if action == sqlite3.SQLITE_FUNCTION and str(arg2).lower() in _BLOCKED_FUNCTIONS:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def sanitize_table_name(name: str) -> str:
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", name)  # drop file extension
    cleaned = re.sub(r"\W+", "_", stem).strip("_").lower() or "table"
    return f"t_{cleaned}" if cleaned[0].isdigit() else cleaned


class DataStore:
    def __init__(self, max_rows: int = 200, timeout_s: float = 8.0):
        self.max_rows = max_rows
        self.timeout_s = timeout_s
        self.frames: dict[str, pd.DataFrame] = {}
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)

    # ---- loading -------------------------------------------------------
    def load_dataframe(self, name: str, df: pd.DataFrame) -> str:
        table = sanitize_table_name(name)
        df = df.copy()
        df.columns = [sanitize_table_name(str(c)) for c in df.columns]
        with self._lock:
            self._conn.set_authorizer(None)  # loading is trusted application code
            df.to_sql(table, self._conn, if_exists="replace", index=False)
            self._conn.set_authorizer(_authorizer)
        self.frames[table] = df
        return table

    def clear(self) -> None:
        """Drop every table (used when a saved session replaces the current data)."""
        with self._lock:
            self._conn.set_authorizer(None)
            for table in self.frames:
                self._conn.execute(f'DROP TABLE IF EXISTS "{table}"')
            self._conn.set_authorizer(_authorizer)
        self.frames.clear()

    # ---- schema --------------------------------------------------------
    @property
    def tables(self) -> list[str]:
        return list(self.frames)

    def schema_text(self) -> str:
        if not self.frames:
            return "No tables loaded."
        lines = []
        for name, df in self.frames.items():
            cols = ", ".join(f"{c} ({_sql_type(df[c])})" for c in df.columns)
            lines.append(f"- {name} [{len(df)} rows]: {cols}")
        return "\n".join(lines)

    def profile_text(self, table: str, sample_rows: int = 5) -> str:
        df = self.frames[table]
        out = [f"Table {table}: {len(df)} rows x {len(df.columns)} columns", ""]
        out.append("| column | type | nulls | distinct | min | max | mean / top values |")
        out.append("|---|---|---|---|---|---|---|")
        for col in df.columns:
            s = df[col]
            nulls, distinct = int(s.isna().sum()), int(s.nunique())
            if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
                lo, hi, extra = _fmt(s.min()), _fmt(s.max()), _fmt(s.mean())
            else:
                lo = hi = ""
                extra = ", ".join(f"{k} ({v})" for k, v in s.value_counts().head(3).items())
            out.append(f"| {col} | {_sql_type(s)} | {nulls} | {distinct} | {lo} | {hi} | {extra[:90]} |")
        dupes = int(df.duplicated().sum())
        out += ["", f"Fully duplicated rows: {dupes}", "", f"Sample ({sample_rows} rows):", ""]
        out.append(df.head(sample_rows).to_markdown(index=False))
        return "\n".join(out)

    # ---- querying ------------------------------------------------------
    def execute(self, sql: str, max_rows: int | None = None) -> QueryResult:
        limit = max_rows or self.max_rows
        deadline = time.monotonic() + self.timeout_s

        def _timeout() -> int:
            return 1 if time.monotonic() > deadline else 0  # non-zero aborts the query

        with self._lock:
            self._conn.set_authorizer(_authorizer)
            self._conn.set_progress_handler(_timeout, 10_000)
            try:
                cur = self._conn.execute(sql)
                columns = [d[0] for d in cur.description or []]
                rows = cur.fetchmany(limit + 1)
            except sqlite3.OperationalError as exc:
                message = "query timed out" if "interrupted" in str(exc) else str(exc)
                raise QueryError(message) from exc
            except sqlite3.DatabaseError as exc:
                raise QueryError(str(exc)) from exc
            finally:
                self._conn.set_progress_handler(None, 0)
        return QueryResult(columns, rows[:limit], truncated=len(rows) > limit)

    def close(self) -> None:
        self._conn.close()


def _sql_type(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(series):
        return "INTEGER"
    if pd.api.types.is_float_dtype(series):
        return "REAL"
    return "TEXT"


def _fmt(value) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".") if pd.notna(value) else ""
