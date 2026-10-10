"""Save and restore a session to disk so an analysis survives a restart.

One folder per saved session under `Settings.sessions_dir`, holding only plain files (JSON, no
pickle): `session.json` plus one JSON file per table and query result. Charts are stored as Plotly
JSON. What is restored is everything the user *sees* (tables, chat, plan, report, queries, charts,
guardrail log) and the grounding evidence. The agent's internal LangGraph memory is not saved, so a
restored conversation continues in a fresh thread: the model sees the new question, not the old chat.
"""

import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import pandas as pd
import plotly.io as pio

from analyst.tools.artifacts import ChartRecord, QueryRecord
from analyst.ui.session import AnalystSession, ChatMessage

FORMAT_VERSION = 1
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_-]+")


def _slug(name: str) -> str:
    return _SAFE_NAME.sub("_", name).strip("_")[:60] or "session"


def _frame_to_json(frame: pd.DataFrame) -> str:
    return frame.to_json(orient="split", date_format="iso")


def _frame_from_json(text: str) -> pd.DataFrame:
    return pd.read_json(StringIO(text), orient="split", convert_dates=False)


def save_session(session: AnalystSession, root: str | Path, name: str | None = None) -> Path:
    """Write the session to `root/<name>/` (overwriting a previous save of the same name)."""
    folder = Path(root) / _slug(name or datetime.now(UTC).strftime("session_%Y%m%d_%H%M%S"))
    (folder / "tables").mkdir(parents=True, exist_ok=True)
    (folder / "queries").mkdir(exist_ok=True)

    for table, frame in session.store.frames.items():
        (folder / "tables" / f"{_slug(table)}.json").write_text(_frame_to_json(frame), encoding="utf-8")
    for q in session.artifacts.queries():
        (folder / "queries" / f"{_slug(q.id)}.json").write_text(_frame_to_json(q.frame), encoding="utf-8")

    meta = {
        "version": FORMAT_VERSION,
        "saved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model_name": session.model_name,
        "require_approval": session.require_approval,
        "guardrails_enabled": session.guards.enabled,
        "tokens": session.tokens,
        "tables": list(session.store.frames),
        "messages": [asdict(m) for m in session.messages],
        "todos": session.todos,
        "files": session.files,
        "queries": [{"id": q.id, "title": q.title, "sql": q.sql} for q in session.artifacts.queries()],
        "charts": [
            {"id": c.id, "title": c.title, "query_id": c.query_id, "figure": c.figure.to_json()}
            for c in session.artifacts.charts()
        ],
        "events": [e.as_dict() for e in session.events.snapshot()],
    }
    (folder / "session.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    return folder


def list_sessions(root: str | Path) -> list[str]:
    """Saved session names, newest first."""
    base = Path(root)
    if not base.is_dir():
        return []
    found = [p for p in base.iterdir() if (p / "session.json").is_file()]
    return [p.name for p in sorted(found, key=lambda p: (p / "session.json").stat().st_mtime, reverse=True)]


def load_session(session: AnalystSession, root: str | Path, name: str) -> None:
    """Restore a saved session into `session`, replacing its current data and conversation."""
    folder = Path(root) / _slug(name)
    meta_path = folder / "session.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"No saved session named '{name}'.")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("version") != FORMAT_VERSION:
        raise ValueError(f"Unsupported session format version {meta.get('version')!r}.")

    session.reset_conversation()
    session.store.clear()
    for table in meta["tables"]:
        frame = _frame_from_json((folder / "tables" / f"{_slug(table)}.json").read_text(encoding="utf-8"))
        session.store.load_dataframe(table, frame)
    session.loaded_files = set(meta["tables"])

    queries = [
        QueryRecord(
            q["id"],
            q["title"],
            q["sql"],
            _frame_from_json((folder / "queries" / f"{_slug(q['id'])}.json").read_text(encoding="utf-8")),
        )
        for q in meta["queries"]
    ]
    charts = [
        ChartRecord(c["id"], c["title"], c["query_id"], pio.from_json(c["figure"])) for c in meta["charts"]
    ]
    session.artifacts.restore(queries, charts)

    # Grounding evidence is rebuilt from what the agent actually saw: its query results.
    for q in queries:
        session.evidence.add_values(q.frame.select_dtypes("number").to_numpy().ravel())
        session.evidence.add_values([len(q.frame)])
    for message in meta["messages"]:
        if message["role"] == "user":
            session.evidence.add_text(message["content"])

    session.messages = [ChatMessage(**m) for m in meta["messages"]]
    session.todos = meta["todos"]
    session.files = meta["files"]
    session.tokens = meta.get("tokens", 0)
    session.model_name = meta.get("model_name", session.model_name)
    session.require_approval = meta.get("require_approval", False)
    session.guards.enabled = meta.get("guardrails_enabled", True)
    session.events.load(meta["events"])
