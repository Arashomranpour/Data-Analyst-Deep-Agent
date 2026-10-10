"""Per-browser-session state: data, guardrails, agent and everything the UI displays."""

import uuid
from dataclasses import dataclass, field

import pandas as pd
from langgraph.checkpoint.memory import MemorySaver

from analyst.agent.builder import build_agent, build_model
from analyst.agent.runner import AgentEvent, AgentRunner
from analyst.config import Settings
from analyst.data.sample import sample_sales_df
from analyst.data.store import DataStore
from analyst.guardrails.events import EventLog
from analyst.guardrails.numbers import Evidence
from analyst.guardrails.suite import GuardrailSuite
from analyst.tools.artifacts import Artifacts
from analyst.tools.toolkit import build_toolkit
from analyst.ui.progress import RunProgress


@dataclass
class ChatMessage:
    role: str  # user | assistant
    content: str
    warnings: list[str] = field(default_factory=list)
    blocked: bool = False


class AnalystSession:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = DataStore(settings.max_rows, settings.query_timeout_s)
        self.events = EventLog()
        self.evidence = Evidence()
        self.artifacts = Artifacts()
        self.guards = GuardrailSuite(
            self.events,
            self.evidence,
            enabled=True,
            injection_detector=settings.injection_detector,
            injection_threshold=settings.injection_threshold,
        )
        self.toolkit = build_toolkit(self.store, self.guards, self.evidence, self.artifacts, settings)
        self.checkpointer = MemorySaver()

        self.thread_id = uuid.uuid4().hex[:12]
        self.messages: list[ChatMessage] = []
        self.trace: list[AgentEvent] = []
        self.todos: list[dict] = []
        self.files: dict[str, str] = {}
        self.pending: AgentEvent | None = None  # a SQL call waiting for human approval
        self.loaded_files: set[str] = set()
        self.tokens = 0
        self.progress = RunProgress()

        self.model_name = settings.groq_model
        self.require_approval = False
        self.runner: AgentRunner | None = None
        self._runner_key: tuple | None = None

    # ---- data ----------------------------------------------------------
    def load_sample(self) -> str:
        table = self.store.load_dataframe("sample_sales", sample_sales_df())
        self.loaded_files.add("sample_sales")
        return table

    def load_csv(self, name: str, frame: pd.DataFrame) -> str:
        return self.store.load_dataframe(name, frame)

    # ---- agent ---------------------------------------------------------
    def ensure_runner(self) -> AgentRunner:
        """(Re)build the agent when a setting that is baked into the graph changes."""
        key = (self.model_name, self.require_approval, self.settings.groq_api_key)
        if self.runner is None or key != self._runner_key:
            agent = build_agent(
                model=build_model(self.settings, self.model_name),
                toolkit=self.toolkit,
                require_approval=self.require_approval,
                checkpointer=self.checkpointer,
            )
            self.runner = AgentRunner(agent, self.guards, self.settings.recursion_limit)
            self._runner_key = key
        return self.runner

    def reset_conversation(self) -> None:
        self.thread_id = uuid.uuid4().hex[:12]
        self.messages.clear()
        self.trace.clear()
        self.todos = []
        self.files = {}
        self.pending = None
        self.progress = RunProgress()
        self.artifacts.clear()
        self.evidence.clear()
        self.events.clear()
        self.runner = None
        self.checkpointer = MemorySaver()

    # ---- event bookkeeping --------------------------------------------
    def record(self, event: AgentEvent) -> None:
        if event.kind == "todos":
            self.todos = event.data["todos"]
        elif event.kind == "interrupt":
            self.pending = event
        elif event.kind == "final":
            self.pending = None
            self.files = event.data["files"]
            self.tokens = event.data.get("tokens", self.tokens)
            self.messages.append(ChatMessage("assistant", event.content, event.data["warnings"]))
        elif event.kind == "blocked":
            self.messages.append(ChatMessage("assistant", event.content, blocked=True))
        elif event.kind == "error":
            self.messages.append(ChatMessage("assistant", f"⚠️ {event.content}", blocked=True))
        if event.kind in ("tool_call", "tool_result", "thought", "file", "interrupt"):
            self.trace.append(event)
