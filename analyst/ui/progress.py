"""Live progress model for one agent run: which pipeline step is active, what finished, how long each
took. Pure logic (no Streamlit) so it is unit-tested; `views.render_progress` only draws it.

The deep agent has no fixed pipeline, so steps are *inferred* from the events it emits: the
subagent that is working, the tool it called, or the plan it wrote.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

from analyst.agent.runner import AgentEvent


@dataclass(frozen=True)
class Stage:
    key: str
    label: str
    icon: str


STAGES: tuple[Stage, ...] = (
    Stage("input", "Input guardrail", "🛡️"),
    Stage("plan", "Plan", "🗺️"),
    Stage("profile", "Profile data", "🔎"),
    Stage("sql", "SQL analysis", "🧮"),
    Stage("chart", "Visualise", "📊"),
    Stage("review", "Critic review", "🕵️"),
    Stage("report", "Write report", "📝"),
    Stage("output", "Output guardrail & answer", "✅"),
)
_BY_AGENT = {"data-profiler": "profile", "sql-analyst": "sql", "visualizer": "chart", "critic": "review"}
_BY_TOOL = {
    "list_tables": "profile",
    "describe_table": "profile",
    "run_sql": "sql",
    "make_chart": "chart",
    "write_file": "report",
    "edit_file": "report",
}

PENDING, ACTIVE, DONE, SKIPPED, WAITING, BLOCKED = (
    "pending",
    "active",
    "done",
    "skipped",
    "waiting",
    "blocked",
)


@dataclass
class StageState:
    status: str = PENDING
    started: float | None = None
    ended: float | None = None
    calls: int = 0  # tool calls attributed to this stage


def stage_for(event: AgentEvent) -> str | None:
    """Which pipeline step an event belongs to (None = it does not move the pipeline)."""
    if event.kind == "todos":
        return "plan"
    if event.kind == "file":
        return "report" if event.name == "/report.md" else None
    if event.kind in ("tool_call", "tool_result", "thought"):
        if event.name == "task":  # the planner delegating: show the subagent's step as soon as it is called
            return _BY_AGENT.get(str(event.data.get("args", {}).get("subagent_type", "")))
        return _BY_AGENT.get(event.agent) or _BY_TOOL.get(event.name)
    return None


class RunProgress:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self.stages = {s.key: StageState() for s in STAGES}
        self.started: float | None = None
        self.ended: float | None = None
        self.running = False
        self.outcome = ""  # "" while running | done | blocked | error | paused
        self.tool_calls = 0
        self.activity = "Idle"
        self.agent = ""
        self.plan_done = 0
        self.plan_total = 0

    # ---- lifecycle -----------------------------------------------------
    def begin(self) -> None:
        """A new question was accepted: reset and mark the input guardrail as passed."""
        self.__init__(self._clock)
        now = self._clock()
        self.started, self.running = now, True
        self.activity = "Checking your question"
        self.stages["input"] = StageState(DONE, now, now)

    def resume(self) -> None:
        """Continue after a human approval pause."""
        self.running, self.outcome, self.ended = True, "", None
        for state in self.stages.values():
            if state.status == WAITING:
                state.status = ACTIVE

    def on_event(self, event: AgentEvent) -> None:
        now = self._clock()
        if event.kind == "blocked":
            self.stages["input"] = StageState(BLOCKED, self.started, now)
            self._end("blocked", "Stopped by the input guardrail", now)
            return
        if event.kind == "error":
            self._end("error", event.content[:90], now)
            return
        if event.kind == "final":
            self._activate("output", now)
            self.stages["output"].status = DONE
            self.stages["output"].ended = now
            self._end("done", "Finished", now)
            return
        if event.kind == "interrupt":
            self._activate("sql", now)
            self.stages["sql"].status = WAITING
            self._end("paused", "Waiting for your approval of a SQL query", now, running=False)
            return

        if event.kind == "todos":
            todos = event.data.get("todos", [])
            self.plan_total = len(todos)
            self.plan_done = sum(t.get("status") == "completed" for t in todos)
        key = stage_for(event)
        if key:
            self._activate(key, now)
            if event.kind == "tool_call":
                self.tool_calls += 1
                self.stages[key].calls += 1
        self.agent = event.agent
        self.activity = self._describe(event)

    # ---- queries -------------------------------------------------------
    @property
    def elapsed(self) -> float:
        if self.started is None:
            return 0.0
        return (self.ended or self._clock()) - self.started

    def duration(self, key: str) -> float | None:
        s = self.stages[key]
        if s.started is None:
            return None
        return (s.ended or (self.ended if not self.running else None) or self._clock()) - s.started

    @property
    def current(self) -> str | None:
        return next((k for k, s in self.stages.items() if s.status in (ACTIVE, WAITING)), None)

    # ---- internals -----------------------------------------------------
    def _activate(self, key: str, now: float) -> None:
        for other, state in self.stages.items():
            if state.status == ACTIVE and other != key:  # one step is in flight at a time
                state.status, state.ended = DONE, now
        state = self.stages[key]
        if state.status in (PENDING, DONE, WAITING):  # a later step may need an earlier one again
            if state.started is None:
                state.started = now
            state.status, state.ended = ACTIVE, None

    def _end(self, outcome: str, activity: str, now: float, running: bool = False) -> None:
        self.outcome, self.activity, self.running, self.ended = outcome, activity, running, now
        for state in self.stages.values():
            if state.status == ACTIVE:
                state.status, state.ended = DONE, now
            elif state.status == PENDING and outcome == "done":
                state.status = SKIPPED  # the agent never needed this step for this question

    @staticmethod
    def _describe(event: AgentEvent) -> str:
        who = event.agent if event.agent != "analyst" else "planner"
        if event.kind == "todos":
            return f"{who} updated the plan"
        if event.kind == "tool_call":
            if event.name == "task":
                return f"{who} delegating to {event.data.get('args', {}).get('subagent_type', 'a subagent')}"
            return f"{who} calling {event.name}"
        if event.kind == "tool_result":
            return f"{who} got a result from {event.name}"
        if event.kind == "file":
            return f"{who} wrote {event.name}"
        return f"{who} is reasoning"
