"""The live progress model (pipeline steps inferred from agent events) and its sidebar rendering."""

import pytest

from analyst.agent.runner import AgentEvent
from analyst.config import Settings
from analyst.ui.progress import ACTIVE, BLOCKED, DONE, PENDING, SKIPPED, WAITING, RunProgress, stage_for
from analyst.ui.session import AnalystSession
from analyst.ui.views import progress_html


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def tick(self, seconds=1.0):
        self.now += seconds


def call(name, agent="analyst", **args):
    return AgentEvent("tool_call", agent, name, data={"args": args})


def status(progress):
    return {k: s.status for k, s in progress.stages.items()}


def test_events_map_to_pipeline_steps():
    assert stage_for(AgentEvent("todos", data={"todos": []})) == "plan"
    assert stage_for(call("run_sql")) == "sql"
    assert stage_for(call("make_chart")) == "chart"
    assert stage_for(call("list_tables")) == "profile"
    assert stage_for(call("task", subagent_type="critic")) == "review"
    assert stage_for(call("anything", agent="sql-analyst")) == "sql"
    assert stage_for(AgentEvent("file", name="/report.md")) == "report"
    assert stage_for(AgentEvent("file", name="/notes.md")) is None
    assert stage_for(AgentEvent("thought", content="hmm")) is None


def test_a_normal_run_walks_the_steps_and_skips_the_unused():
    clock = Clock()
    p = RunProgress(clock)
    p.begin()
    assert status(p)["input"] == DONE and p.running

    clock.tick(2)
    p.on_event(AgentEvent("todos", data={"todos": [{"status": "completed"}, {"status": "pending"}]}))
    assert (p.plan_done, p.plan_total) == (1, 2) and p.current == "plan"

    clock.tick(1)
    p.on_event(call("run_sql"))
    assert status(p)["plan"] == DONE and status(p)["sql"] == ACTIVE and p.tool_calls == 1
    assert p.stages["sql"].calls == 1

    clock.tick(3)
    p.on_event(call("make_chart"))
    p.on_event(AgentEvent("file", name="/report.md"))
    clock.tick(1)
    p.on_event(AgentEvent("final", content="ok"))

    assert not p.running and p.outcome == "done"
    s = status(p)
    assert s["sql"] == s["chart"] == s["report"] == s["output"] == DONE
    assert s["profile"] == s["review"] == SKIPPED
    assert p.elapsed == pytest.approx(7.0)
    assert p.duration("sql") == pytest.approx(3.0)


def test_only_one_step_is_in_flight_even_when_the_agent_goes_back():
    p = RunProgress(Clock())
    p.begin()
    for event in (call("run_sql"), call("make_chart"), call("run_sql")):
        p.on_event(event)
    assert [k for k, s in p.stages.items() if s.status == ACTIVE] == ["sql"]
    assert p.stages["sql"].calls == 2 and p.stages["chart"].status == DONE


def test_blocked_input_stops_at_the_first_step():
    p = RunProgress(Clock())
    p.begin()
    p.on_event(AgentEvent("blocked", content="nope"))
    assert p.outcome == "blocked" and not p.running
    assert status(p)["input"] == BLOCKED and status(p)["sql"] == PENDING  # not "skipped": it never ran


def test_approval_pause_waits_on_sql_and_resume_continues():
    p = RunProgress(Clock())
    p.begin()
    p.on_event(AgentEvent("interrupt", name="run_sql"))
    assert p.outcome == "paused" and p.stages["sql"].status == WAITING and p.current == "sql"
    p.resume()
    assert p.running and p.stages["sql"].status == ACTIVE and p.outcome == ""


def test_error_ends_the_run_without_marking_steps_skipped():
    p = RunProgress(Clock())
    p.begin()
    p.on_event(call("run_sql"))
    p.on_event(AgentEvent("error", content="rate limit"))
    assert p.outcome == "error" and status(p)["sql"] == DONE and status(p)["chart"] == PENDING


def test_begin_resets_a_previous_run():
    p = RunProgress(Clock())
    p.begin()
    p.on_event(call("run_sql"))
    p.begin()
    assert p.tool_calls == 0 and status(p)["sql"] == PENDING


def test_html_escapes_untrusted_text():
    session = AnalystSession(Settings(llm_backend="fake"))
    p = RunProgress(Clock())
    p.begin()
    p.on_event(AgentEvent("tool_call", "<img src=x onerror=alert(1)>", "run_sql", data={"args": {}}))
    page = progress_html(p, session)
    assert "<img src=x" not in page and "&lt;img" in page
    assert "SQL analysis" in page and "lp-running" in page
