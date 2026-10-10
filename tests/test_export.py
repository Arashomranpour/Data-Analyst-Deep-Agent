"""Report export (Markdown / HTML) and the guardrail audit log."""

import csv
import io
import json

import pandas as pd
import plotly.graph_objects as go

from analyst.export.report import build_html, build_markdown
from analyst.guardrails.events import EventLog
from analyst.tools.artifacts import ChartRecord, QueryRecord


def _query(sql="SELECT 1"):
    return QueryRecord("q1", "Revenue", sql, pd.DataFrame({"region": ["N", "S"], "revenue": [10, 20]}))


def _chart():
    return ChartRecord("c1", "Revenue by region", "q1", go.Figure(go.Bar(x=["N", "S"], y=[10, 20])))


def _events():
    log = EventLog()
    log.add("input", "PromptInjection", "passed")
    log.add("sql", "SafeSQL", "blocked", "DELETE not allowed")
    log.add("output", "PIIRedactor", "fixed", "2 emails")
    return log


def test_markdown_has_report_queries_and_guardrail_summary():
    md = build_markdown("# Revenue report\nNorth leads.", [_query()], _events())
    assert md.startswith("# Revenue report")
    assert "```sql\nSELECT 1\n```" in md and "| region" in md
    assert "Appendix B" in md and "`SafeSQL`" in md


def test_html_is_complete_and_contains_charts_and_appendix():
    page = build_html(
        "# Revenue report\n\n| a | b |\n|---|---|\n| 1 | 2 |", [_chart()], [_query()], _events()
    )
    assert page.startswith("<!doctype html>") and page.rstrip().endswith("</html>")
    assert "<h1>Revenue report</h1>" in page and "<table>" in page
    assert "Revenue by region" in page and "plotly" in page.lower()
    assert "Appendix A" in page and "SELECT 1" in page


def test_html_export_cannot_be_hijacked_by_markup_in_the_report_or_data():
    evil = '<script>alert("x")</script> <img src=x onerror=alert(1)>'
    page = build_html(f"# Report\n{evil}", [], [_query(f"SELECT '{evil}'")], _events(), title=evil)
    assert "<script>alert" not in page and "<img src=x" not in page
    assert "&lt;script&gt;" in page


def test_inline_plotly_embeds_the_library_for_offline_use():
    cdn = build_html("# R", [_chart()], [], _events())
    inline = build_html("# R", [_chart()], [], _events(), inline_plotly=True)
    assert len(inline) > len(cdn) + 1_000_000


def test_audit_summary_counts_by_stage_and_validator():
    summary = _events().summary()
    assert summary["total"] == 3
    assert summary["by_status"] == {"passed": 1, "fixed": 1, "blocked": 1, "warning": 0}
    assert summary["by_validator"]["SafeSQL"]["blocked"] == 1
    assert summary["by_stage"]["output"]["fixed"] == 1


def test_audit_json_and_csv_round_trip():
    log = _events()
    data = json.loads(log.to_json())
    assert data["summary"]["total"] == 3 and len(data["events"]) == 3
    assert data["events"][0]["at"].endswith("+00:00")

    rows = list(csv.DictReader(io.StringIO(log.to_csv())))
    assert [r["validator"] for r in rows] == ["PromptInjection", "SafeSQL", "PIIRedactor"]
    assert rows[1]["detail"] == "DELETE not allowed"


def test_event_log_load_replaces_contents():
    source = _events()
    target = EventLog()
    target.add("input", "x", "passed")
    target.load([e.as_dict() for e in source.snapshot()])
    assert [e.validator for e in target.snapshot()] == ["PromptInjection", "SafeSQL", "PIIRedactor"]
