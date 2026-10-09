import pytest

from analyst.data.sample import POISONED_NOTES, sample_sales_df
from analyst.data.store import DataStore, QueryError, sanitize_table_name


def test_sample_dataset_is_deterministic_and_has_the_planted_problems():
    a, b = sample_sales_df(), sample_sales_df()
    assert a.equals(b)
    assert a.duplicated().sum() == 3  # duplicated rows to find
    assert a["discount"].isna().sum() > 0
    assert a["notes"].dropna().str.contains("IGNORE ALL PREVIOUS", case=False).any()


def test_table_name_sanitising():
    assert sanitize_table_name("My Sales (2024).csv") == "my_sales_2024"
    assert sanitize_table_name("2024.csv") == "t_2024"


def test_execute_and_row_cap(env):
    result = env.store.execute("SELECT region FROM sample_sales", max_rows=10)
    assert len(result.rows) == 10 and result.truncated
    small = env.store.execute("SELECT DISTINCT region FROM sample_sales ORDER BY region")
    assert [r[0] for r in small.rows] == ["East", "North", "South", "West"] and not small.truncated


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE sample_sales",
        "DELETE FROM sample_sales",
        "INSERT INTO sample_sales (order_id) VALUES (1)",
        "UPDATE sample_sales SET revenue = 0",
        "PRAGMA table_info(sample_sales)",
        "ATTACH DATABASE ':memory:' AS x",
        "CREATE TABLE x (a)",
    ],
)
def test_store_enforces_read_only_even_without_guardrails(sql):
    """Defence in depth: SQLite's authorizer blocks writes if a guard ever fails."""
    store = DataStore()
    store.load_dataframe("t", sample_sales_df(20))
    with pytest.raises(QueryError):
        store.execute(sql)
    assert store.execute("SELECT COUNT(*) FROM t").rows[0][0] >= 20


def test_runaway_query_times_out():
    store = DataStore(timeout_s=0.3)
    store.load_dataframe("t", sample_sales_df(10))
    with pytest.raises(QueryError, match="timed out"):
        store.execute("WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r) SELECT COUNT(*) FROM r")


# ------------------------------------------------------------------------------ tools
def test_run_sql_returns_table_query_id_and_records_evidence(env):
    out = env.toolkit.run_sql.invoke(
        {
            "query": "SELECT region, ROUND(SUM(revenue),2) AS total FROM sample_sales GROUP BY region",
            "title": "By region",
        }
    )
    assert "query_id: q1" in out and "| region" in out and "rows: 4" in out
    assert env.artifacts.get_query("q1").title == "By region"
    total = env.store.execute("SELECT ROUND(SUM(revenue),2) FROM sample_sales WHERE region='North'").rows[0][
        0
    ]
    assert any(abs(v - total) < 0.01 for v in env.evidence.array())


def test_run_sql_blocks_destructive_queries_and_tells_the_model(env):
    out = env.toolkit.run_sql.invoke({"query": "DROP TABLE sample_sales"})
    assert out.startswith("BLOCKED by guardrail (SafeSQL)")
    assert env.store.execute("SELECT COUNT(*) FROM sample_sales").rows[0][0] > 0


def test_run_sql_reports_sql_errors_instead_of_raising(env):
    out = env.toolkit.run_sql.invoke({"query": "SELECT nope FROM sample_sales"})
    assert out.startswith("SQL error")


def test_poisoned_cells_never_reach_the_model(env):
    out = env.toolkit.run_sql.invoke(
        {"query": "SELECT order_id, notes FROM sample_sales WHERE notes IS NOT NULL"}
    )
    assert "removed: possible prompt injection" in out
    assert "gift wrapping" in out  # benign note survives
    for poisoned in POISONED_NOTES:
        assert poisoned[:30].lower() not in out.lower()


def test_pii_is_masked_in_tool_results(env):
    out = env.toolkit.run_sql.invoke({"query": "SELECT customer_email, phone FROM sample_sales LIMIT 3"})
    assert "[EMAIL]" in out and "[PHONE]" in out
    assert "@example.com" not in out


def test_without_guardrails_the_attack_text_gets_through(env_unguarded):
    """The control experiment that makes the demo meaningful."""
    out = env_unguarded.toolkit.run_sql.invoke(
        {"query": "SELECT notes FROM sample_sales WHERE notes LIKE 'IGNORE%'"}
    )
    assert "IGNORE ALL PREVIOUS INSTRUCTIONS" in out


def test_describe_table_profile(env):
    out = env.toolkit.describe_table.invoke({"table": "sample_sales"})
    assert "Fully duplicated rows: 3" in out and "| discount |" in out
    assert "Unknown table" in env.toolkit.describe_table.invoke({"table": "nope"})


def test_make_chart(env):
    env.toolkit.run_sql.invoke(
        {"query": "SELECT region, SUM(revenue) AS t FROM sample_sales GROUP BY region"}
    )
    ok = env.toolkit.make_chart.invoke({"query_id": "q1", "chart_type": "bar", "x": "region", "y": "t"})
    assert "chart_id c1" in ok and len(env.artifacts.charts()) == 1
    assert "Unknown query_id" in env.toolkit.make_chart.invoke(
        {"query_id": "q9", "chart_type": "bar", "x": "region", "y": "t"}
    )
    assert "not in" in env.toolkit.make_chart.invoke(
        {"query_id": "q1", "chart_type": "bar", "x": "nope", "y": "t"}
    )
    assert "needs a y" in env.toolkit.make_chart.invoke(
        {"query_id": "q1", "chart_type": "line", "x": "region"}
    )
