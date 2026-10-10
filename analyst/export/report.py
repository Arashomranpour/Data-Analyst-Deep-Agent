"""Turn a finished analysis into a document you can keep: Markdown, or a self-contained HTML page
(print it to PDF from the browser). Pure functions over the session's artifacts, no UI code.

Security note: the report text is model output and may echo poisoned cell content, so the HTML
builder escapes all raw HTML in it before rendering Markdown. Nothing from the data can inject
markup or scripts into the exported page.
"""

import html
from datetime import UTC, datetime

import markdown

from analyst.guardrails.events import EventLog
from analyst.tools.artifacts import ChartRecord, QueryRecord

_CSS = """
body{font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;color:#1f2933}
h1,h2,h3{line-height:1.25} table{border-collapse:collapse;margin:1rem 0;font-size:.92em}
th,td{border:1px solid #cbd2d9;padding:.35rem .6rem;text-align:left} th{background:#f0f4f8}
pre{background:#f0f4f8;padding:.8rem;overflow-x:auto;border-radius:6px} .meta{color:#627d98;font-size:.85em}
.chart{margin:1.5rem 0;page-break-inside:avoid} @media print{body{margin:0}.noprint{display:none}}
"""
_MAX_APPENDIX_ROWS = 25


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _guardrail_lines(events: EventLog) -> list[str]:
    counts = events.counts()
    if not events.snapshot():
        return ["No guardrail checks were recorded."]
    return (
        [f"- {status}: {count}" for status, count in counts.items()]
        + [""]
        + [
            f"- `{name}`: " + ", ".join(f"{k} {v}" for k, v in row.items() if v)
            for name, row in events.summary()["by_validator"].items()
        ]
    )


def build_markdown(
    report: str, queries: list[QueryRecord], events: EventLog, title: str = "Analysis report"
) -> str:
    """The agent's `/report.md` plus an appendix: every SQL query it ran and the guardrail summary."""
    parts = [report.strip() or f"# {title}", "", "---", "", "## Appendix A - Queries run", ""]
    if not queries:
        parts.append("_No queries were run._")
    for q in queries:
        parts += [f"### {q.id} - {q.title}", "", "```sql", q.sql.strip(), "```", ""]
        parts.append(q.frame.head(_MAX_APPENDIX_ROWS).to_markdown(index=False))
        if len(q.frame) > _MAX_APPENDIX_ROWS:
            parts.append(f"\n_Showing {_MAX_APPENDIX_ROWS} of {len(q.frame)} rows._")
        parts.append("")
    parts += [
        "## Appendix B - Guardrail summary",
        "",
        *_guardrail_lines(events),
        "",
        f"_Generated {_stamp()}_",
        "",
    ]
    return "\n".join(parts)


def build_html(
    report: str,
    charts: list[ChartRecord],
    queries: list[QueryRecord],
    events: EventLog,
    title: str = "Analysis report",
    inline_plotly: bool = False,
) -> str:
    """Self-contained HTML. Charts load plotly.js from a CDN unless `inline_plotly` embeds it (~4 MB,
    works fully offline)."""
    body = markdown.markdown(html.escape(report.strip()), extensions=["tables", "fenced_code"])
    chart_html = []
    for i, chart in enumerate(charts):
        include = True if (inline_plotly and i == 0) else ("cdn" if i == 0 else False)
        chart_html.append(
            f'<div class="chart"><h3>{html.escape(chart.title)}</h3>'
            f"{chart.figure.to_html(full_html=False, include_plotlyjs=include)}</div>"
        )
    query_html = []
    for q in queries:
        table = q.frame.head(_MAX_APPENDIX_ROWS).to_html(index=False, border=0, escape=True)
        query_html.append(
            f"<h3>{html.escape(q.id)} - {html.escape(q.title)}</h3>"
            f"<pre>{html.escape(q.sql.strip())}</pre>{table}"
        )
    guard = markdown.markdown(html.escape("\n".join(_guardrail_lines(events))))
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head><body>"
        f'<p class="meta">Generated {_stamp()} by Data Analyst Deep Agent</p>'
        f"{body}"
        f"{'<h2>Charts</h2>' + ''.join(chart_html) if chart_html else ''}"
        f"<h2>Appendix A - Queries run</h2>{''.join(query_html) or '<p><em>No queries were run.</em></p>'}"
        f"<h2>Appendix B - Guardrail summary</h2>{guard}"
        f"</body></html>"
    )
