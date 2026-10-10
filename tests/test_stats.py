"""Statistics tools: the pure functions, then the agent-facing tools against the sample data."""

import numpy as np
import pandas as pd
import pytest

from analyst.tools import stats


@pytest.fixture
def rng():
    return np.random.default_rng(7)


# -------------------------------------------------------------------------- correlate
def test_correlate_finds_the_strong_pair_first(rng):
    x = rng.normal(size=80)
    frame = pd.DataFrame({"x": x, "y": 2 * x + rng.normal(scale=0.1, size=80), "noise": rng.normal(size=80)})
    text = stats.correlate(frame)
    first = text.splitlines()[4]  # title, blank, header, separator, then the strongest row
    assert "x" in first and "y" in first and "strong positive" in first
    assert "does not show causation" in text


def test_correlate_spearman_and_bad_input(rng):
    frame = pd.DataFrame({"a": range(20), "b": [v**3 for v in range(20)]})
    assert "Spearman" in stats.correlate(frame, method="spearman")
    assert "method must be" in stats.correlate(frame, method="kendall")
    assert "Unknown columns" in stats.correlate(frame, columns=["a", "zzz"])
    assert "at least two" in stats.correlate(frame, columns=["a"])
    assert "No column pair" in stats.correlate(pd.DataFrame({"a": [1, 1, 1, 1], "b": [1, 2, 3, 4]}))


# ---------------------------------------------------------------------- compare groups
def test_compare_two_groups_detects_a_real_difference(rng):
    frame = pd.DataFrame(
        {"v": np.r_[rng.normal(10, 1, 40), rng.normal(14, 1, 40)], "g": ["a"] * 40 + ["b"] * 40}
    )
    text = stats.compare_groups(frame, "v", "g")
    assert "Welch t-test" in text and "Mann-Whitney" in text and "differ significantly" in text
    assert "do not differ" not in text


def test_compare_groups_no_difference_and_anova(rng):
    pattern = [4, 5, 6, 5, 6, 4, 6, 4, 5]  # every group sees the same values, so no difference
    same = pd.DataFrame({"v": pattern * 10, "g": ["a", "b", "c"] * 30})
    text = stats.compare_groups(same, "v", "g")
    assert "ANOVA" in text and "Kruskal" in text and "do not differ significantly" in text


def test_compare_groups_validates_input():
    frame = pd.DataFrame({"v": [1, 2, 3, 4], "g": ["a", "a", "b", "c"]})
    assert "at least two groups" in stats.compare_groups(frame, "v", "g")
    assert "not in" in stats.compare_groups(frame, "nope", "g")
    assert "not in" in stats.compare_groups(frame, "v", "nope")
    assert "no numeric values" in stats.compare_groups(
        pd.DataFrame({"v": ["x", "y"], "g": ["a", "b"]}), "v", "g"
    )


# ---------------------------------------------------------------------------- outliers
def test_outliers_iqr_and_zscore():
    frame = pd.DataFrame({"id": range(12), "v": [10, 11, 9, 10, 12, 10, 11, 9, 10, 11, 10, 500]})
    iqr = stats.find_outliers(frame, "v")
    assert "1 of 12" in iqr and "500" in iqr
    z = stats.find_outliers(frame, "v", method="zscore", threshold=2.5)
    assert "z-score rule" in z and "500" in z
    assert "constant" in stats.find_outliers(pd.DataFrame({"v": [3.0] * 6}), "v", method="zscore")
    assert "method must be" in stats.find_outliers(frame, "v", method="magic")
    assert "at least 4" in stats.find_outliers(frame.head(3), "v")


def test_clean_column_reports_no_outliers():
    assert "0 of" in stats.find_outliers(pd.DataFrame({"v": [10, 11, 10, 12, 11, 10, 11]}), "v")


# ---------------------------------------------------------------------------- forecast
def test_forecast_extends_a_dated_trend():
    months = pd.date_range("2024-01-01", periods=12, freq="MS").strftime("%Y-%m-%d")
    frame = pd.DataFrame({"month": months, "revenue": [100 + 10 * i + (i % 2) for i in range(12)]})
    text, fig = stats.forecast(frame, "month", "revenue", periods=3)
    assert "rising" in text and "lower_95" in text and "2025-01" in text
    assert text.count("\n|") >= 4  # header + separator + 3 forecast rows
    assert fig is not None and len(fig.data) == 3
    assert "straight line" in text


def test_forecast_numeric_axis_and_guards():
    frame = pd.DataFrame({"t": range(1, 9), "y": [50 - 2 * i for i in range(8)]})
    text, fig = stats.forecast(frame, "t", "y", periods=2)
    assert "falling" in text and fig is not None
    assert "at least 6" in stats.forecast(frame.head(4), "t", "y")[0]
    assert "between 1 and 24" in stats.forecast(frame, "t", "y", periods=99)[0]
    assert stats.forecast(frame, "missing", "y")[1] is None


# ------------------------------------------------------------- through the agent toolkit
def run(env, sql):
    return env.toolkit.run_sql.invoke({"query": sql, "title": "t"})


def test_correlate_tool_uses_a_previous_query_and_unknown_ids_are_explained(env):
    out = run(env, "SELECT units, unit_price, revenue FROM sample_sales")
    assert "query_id: q1" in out
    text = env.toolkit.correlate.invoke({"query_id": "q1"})
    assert "Pearson" in text and "revenue" in text
    assert "Unknown query_id" in env.toolkit.correlate.invoke({"query_id": "q99"})


def test_compare_groups_and_outlier_tools_on_sample_data(env):
    run(env, "SELECT region, revenue FROM sample_sales")
    assert "ANOVA" in env.toolkit.compare_groups.invoke(
        {"query_id": "q1", "value_column": "revenue", "group_column": "region"}
    )
    out = env.toolkit.find_outliers.invoke({"query_id": "q1", "column": "revenue"})
    assert "outliers" in out  # the sample data deliberately contains a revenue outlier


def test_forecast_tool_creates_a_chart_and_the_numbers_count_as_evidence(env):
    run(
        env,
        "SELECT substr(order_date, 1, 7) AS month, SUM(revenue) AS revenue FROM sample_sales GROUP BY 1 ORDER BY 1",
    )
    before = len(env.artifacts.charts())
    text = env.toolkit.forecast.invoke(
        {"query_id": "q1", "time_column": "month", "value_column": "revenue", "periods": 2}
    )
    assert "Chart created" in text and len(env.artifacts.charts()) == before + 1
    assert env.evidence.array().size > 0


def test_tool_output_is_still_sanitised(env):
    run(env, "SELECT customer_email AS e, revenue FROM sample_sales")
    out = env.toolkit.find_outliers.invoke({"query_id": "q1", "column": "revenue"})
    assert "@example.com" not in out  # PII in outlier rows is masked by the tool-output guard


def test_the_statistician_is_a_real_subagent_with_the_stats_tools(env):
    runner = env.runner()
    assert runner.agent is not None
    names = {t.name for t in env.toolkit.statistics}
    assert names == {"correlate", "compare_groups", "find_outliers", "forecast"}
