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
from analyst.tools import stats
from analyst.tools.artifacts import Artifacts

ChartType = Literal["bar", "line", "scatter", "pie", "histogram", "box"]


@dataclass
class Toolkit:
    list_tables: BaseTool
    describe_table: BaseTool
    run_sql: BaseTool
    make_chart: BaseTool
    correlate: BaseTool
    compare_groups: BaseTool
    find_outliers: BaseTool
    forecast: BaseTool

    @property
    def all(self) -> list[BaseTool]:
        return [
            self.list_tables,
            self.describe_table,
            self.run_sql,
            self.make_chart,
            self.correlate,
            self.compare_groups,
            self.find_outliers,
            self.forecast,
        ]

    @property
    def statistics(self) -> list[BaseTool]:
        return [self.correlate, self.compare_groups, self.find_outliers, self.forecast]


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

    def result_frame(query_id: str):
        record = artifacts.get_query(query_id)
        if record is None:
            return None, f"Unknown query_id '{query_id}'. Existing: {[q.id for q in artifacts.queries()]}"
        return record.frame, ""

    @tool
    def correlate(
        query_id: str,
        columns: list[str] | None = None,
        method: Literal["pearson", "spearman"] = "pearson",
    ) -> str:
        """Correlation between the numeric columns of a previous query result (strongest pairs first, with
        p-values and sample sizes). `columns` defaults to every numeric column. Use spearman for
        non-linear or outlier-heavy data."""
        frame, error = result_frame(query_id)
        return error if frame is None else seen(stats.correlate(frame, columns, method))

    @tool
    def compare_groups(query_id: str, value_column: str, group_column: str) -> str:
        """Test whether a numeric column differs between the groups of a categorical column in a previous
        query result: group summary, then Welch t-test + Mann-Whitney (2 groups) or ANOVA + Kruskal-Wallis
        (3+ groups) with an effect size. The query must return one row per observation, not per group."""
        frame, error = result_frame(query_id)
        return error if frame is None else seen(stats.compare_groups(frame, value_column, group_column))

    @tool
    def find_outliers(
        query_id: str,
        column: str,
        method: Literal["iqr", "zscore"] = "iqr",
        threshold: float | None = None,
    ) -> str:
        """List outliers of one numeric column in a previous query result, with the rule and bounds used.
        iqr (default k=1.5) is robust; zscore (default 3) assumes a roughly normal column."""
        frame, error = result_frame(query_id)
        return error if frame is None else seen(stats.find_outliers(frame, column, method, threshold))

    @tool
    def forecast(query_id: str, time_column: str, value_column: str, periods: int = 3) -> str:
        """Extrapolate a linear trend for the next `periods` (1-24) steps of a time series from a previous
        query result, with a 95% prediction interval, and create a chart of it. Needs 6+ points. It is
        a simple trend line, not a seasonal model: say so when you report it."""
        frame, error = result_frame(query_id)
        if frame is None:
            return error
        text, figure = stats.forecast(frame, time_column, value_column, periods)
        if figure is None:
            return text
        cid = artifacts.add_chart(f"{value_column}: trend forecast", query_id, figure)
        return seen(f"{text}\n\nChart created (chart_id {cid}).")

    return Toolkit(
        list_tables=list_tables,
        describe_table=describe_table,
        run_sql=run_sql,
        make_chart=make_chart,
        correlate=correlate,
        compare_groups=compare_groups,
        find_outliers=find_outliers,
        forecast=forecast,
    )
