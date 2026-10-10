"""Saving a finished analysis and restoring it into a fresh session."""

import json

import pytest
from pandas.testing import assert_frame_equal

from analyst.config import Settings
from analyst.persistence import list_sessions, load_session, save_session
from analyst.ui.session import AnalystSession, ChatMessage


def _new() -> AnalystSession:
    return AnalystSession(Settings(llm_backend="fake"))


def assert_same_frame(left, right):
    """Equal values; a missing cell may come back as NaN where it was None."""
    assert_frame_equal(left.fillna(""), right.fillna(""), check_dtype=False)


def _finished_session() -> AnalystSession:
    session = _new()
    session.load_sample()
    session.messages.append(ChatMessage("user", "Which region has the highest revenue?"))
    for event in session.ensure_runner().ask("Which region has the highest revenue?", session.thread_id):
        session.record(event)
    assert session.artifacts.charts() and session.files.get("/report.md")
    return session


def test_round_trip_restores_everything_the_user_sees(tmp_path):
    original = _finished_session()
    save_session(original, tmp_path, "run one")

    restored = _new()
    load_session(restored, tmp_path, "run one")

    assert restored.store.tables == original.store.tables
    assert_same_frame(restored.store.frames["sample_sales"], original.store.frames["sample_sales"])
    assert [m.content for m in restored.messages] == [m.content for m in original.messages]
    assert restored.files == original.files and restored.todos == original.todos
    assert [q.sql for q in restored.artifacts.queries()] == [q.sql for q in original.artifacts.queries()]
    assert_same_frame(restored.artifacts.queries()[0].frame, original.artifacts.queries()[0].frame)
    assert [c.title for c in restored.artifacts.charts()] == [c.title for c in original.artifacts.charts()]
    assert len(restored.events.snapshot()) == len(original.events.snapshot())
    assert restored.tokens == original.tokens


def test_restored_session_can_be_queried_and_keeps_grounding_evidence(tmp_path):
    original = _finished_session()
    save_session(original, tmp_path, "x")
    restored = _new()
    load_session(restored, tmp_path, "x")

    assert restored.store.execute("SELECT COUNT(*) FROM sample_sales").rows[0][0] > 0
    assert restored.evidence.array().size > 0
    events = list(restored.ensure_runner().ask("Which region has the highest revenue?", restored.thread_id))
    assert events[-1].kind == "final" and events[-1].data["warnings"] == []


def test_restore_replaces_old_tables(tmp_path):
    saved = _new()
    saved.load_sample()
    save_session(saved, tmp_path, "s")

    other = _new()
    other.load_csv("leftover.csv", saved.store.frames["sample_sales"].head(3))
    load_session(other, tmp_path, "s")
    assert other.store.tables == ["sample_sales"]
    with pytest.raises(Exception, match="no such table"):
        other.store.execute("SELECT * FROM leftover")


def test_list_sessions_newest_first_and_names_are_sanitised(tmp_path):
    session = _new()
    session.load_sample()
    save_session(session, tmp_path, "first")
    path = save_session(session, tmp_path, "../../evil name")
    assert path.parent == tmp_path  # no path traversal
    assert list_sessions(tmp_path)[0] == path.name and len(list_sessions(tmp_path)) == 2
    assert list_sessions(tmp_path / "missing") == []


def test_missing_or_incompatible_sessions_fail_clearly(tmp_path):
    session = _new()
    with pytest.raises(FileNotFoundError):
        load_session(session, tmp_path, "ghost")
    folder = tmp_path / "old"
    folder.mkdir()
    (folder / "session.json").write_text(json.dumps({"version": 99}), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported session format"):
        load_session(session, tmp_path, "old")
