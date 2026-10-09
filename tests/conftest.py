import pytest

from analyst.agent.builder import build_agent, build_model
from analyst.agent.runner import AgentRunner
from analyst.config import Settings
from analyst.data.sample import sample_sales_df
from analyst.data.store import DataStore
from analyst.guardrails.events import EventLog
from analyst.guardrails.numbers import Evidence
from analyst.guardrails.suite import GuardrailSuite
from analyst.tools.artifacts import Artifacts
from analyst.tools.toolkit import build_toolkit


class Env:
    """One wired-up analyst session (store + guardrails + tools) for tests."""

    def __init__(self, guardrails: bool = True):
        self.settings = Settings(llm_backend="fake", max_rows=200)
        self.store = DataStore(max_rows=self.settings.max_rows)
        self.table = self.store.load_dataframe("sample_sales", sample_sales_df())
        self.events, self.evidence, self.artifacts = EventLog(), Evidence(), Artifacts()
        self.guards = GuardrailSuite(self.events, self.evidence, enabled=guardrails)
        self.toolkit = build_toolkit(self.store, self.guards, self.evidence, self.artifacts, self.settings)

    def runner(self, require_approval: bool = False) -> AgentRunner:
        agent = build_agent(
            model=build_model(self.settings), toolkit=self.toolkit, require_approval=require_approval
        )
        return AgentRunner(agent, self.guards)


@pytest.fixture
def env() -> Env:
    return Env()


@pytest.fixture
def env_unguarded() -> Env:
    return Env(guardrails=False)
