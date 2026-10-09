"""The agent's tools. Every tool goes through the guardrail suite and returns problems as
text (never raises), so the model can read the message and correct itself."""

from dataclasses import dataclass
from typing import Literal

import plotly.express as px
from langchain_core.tools import BaseTool, tool

from analyst.config import Settings
from analyst.data.store import DataStore, QueryError
from analyst.guardrails.numbers import Evidence
from analyst.guardrails.suite import GuardrailBlocked, GuardrailSuite
from analyst.tools.artifacts import Artifacts

ChartType = Literal["bar", "line", "scatter", "pie", "histogram", "box"]


@dataclass
class Toolkit:
    list_tables: BaseTool
    describe_table: BaseTool
    run_sql: BaseTool
    make_chart: BaseTool

    @property
    def all(self) -> list[BaseTool]:
        return [self.list_tables, self.describe_table, self.run_sql, self.make_chart]


def build_toolkit(
    store: DataStore,
    guards: GuardrailSuite,
    evidence: Evidence,
    artifacts: Artifacts,
    settings: Settings,
) -> Toolkit:
    def seen(text: str) -> str:
        """Record what the model is about to see, then sanitise it."""
        evidence.add_text(text)
        return guards.sanitize_tool_output(text)

    @tool
    def list_tables() -> str:
        """List the available tables with their columns, types and row counts."""
        return seen(store.schema_text())

    @tool
    def describe_table(table: str) -> str:
        """Profile one table: per-column type, nulls, distinct values, min/max/mean, duplicate
        rows and a few sample rows. Use it to understand the data and spot quality problems."""
        if table not in store.frames:
            return f"Unknown table '{table}'. Available: {store.tables}"
        return seen(store.profile_text(table))

    @tool
    def run_sql(query: str, title: str = "") -> str:
        """Run ONE read-only SQL SELECT (SQLite dialect) and get the result as a markdown table.
        Returns a query_id you can pass to make_chart. Only SELECT/WITH queries are allowed; a
        row limit is added automatically. Give the query a short descriptive `title`."""
        try:
            safe_sql = guards.check_sql(query, store.tables, settings.max_rows)
        except GuardrailBlocked as exc:
            return f"BLOCKED by guardrail ({exc.validator}): {exc.reason}"
        try:
            result = store.execute(safe_sql)
        except QueryError as exc:
            return f"SQL error: {exc}. Check column names with describe_table and retry."

        frame = result.to_frame()
        shown = frame.head(settings.preview_rows)
        evidence.add_values(shown.select_dtypes("number").to_numpy().ravel())
        evidence.add_values([len(frame)])
        qid = artifacts.add_query(title, safe_sql, frame)

        note = " (truncated at the row cap)" if result.truncated else ""
        more = f"\n... {len(frame) - len(shown)} more rows not shown" if len(frame) > len(shown) else ""
        body = shown.to_markdown(index=False) if len(frame) else "(no rows)"
        return seen(f"query_id: {qid}\nrows: {len(frame)}{note}\n\n{body}{more}")

    @tool
    def make_chart(
        query_id: str,
        chart_type: ChartType,
        x: str,
        y: str | None = None,
        color: str | None = None,
        title: str = "",
    ) -> str:
        """Create a chart from a previous query result. chart_type: bar, line, scatter, pie,
        histogram or box. `x` (and `y` for everything except histogram) are column names of
        that query. For pie: x = labels, y = values."""
        record = artifacts.get_query(query_id)
        if record is None:
            known = [q.id for q in artifacts.queries()]
            return f"Unknown query_id '{query_id}'. Existing: {known}"
        frame = record.frame
        for name, col in (("x", x), ("y", y), ("color", color)):
            if col is not None and col not in frame.columns:
                return f"Column '{col}' (for {name}) not in {list(frame.columns)}."
        if chart_type != "histogram" and y is None:
            return f"chart_type '{chart_type}' needs a y column."
        label = title or record.title

        try:
            if chart_type == "bar":
                fig = px.bar(frame, x=x, y=y, color=color, title=label)
            elif chart_type == "line":
                fig = px.line(frame, x=x, y=y, color=color, title=label, markers=True)
            elif chart_type == "scatter":
                fig = px.scatter(frame, x=x, y=y, color=color, title=label)
            elif chart_type == "pie":
                fig = px.pie(frame, names=x, values=y, title=label)
            elif chart_type == "histogram":
                fig = px.histogram(frame, x=x, color=color, title=label)
            else:
                fig = px.box(frame, x=color, y=x if y is None else y, title=label)
        except Exception as exc:  # plotly raises on incompatible data
            return f"Could not build the chart: {exc}"
        fig.update_layout(template="plotly_white", margin={"t": 60, "l": 10, "r": 10, "b": 10})
        cid = artifacts.add_chart(label, query_id, fig)
        return f"Chart '{label}' created (chart_id {cid})."

    return Toolkit(list_tables, describe_table, run_sql, make_chart)
