"""Runs the deep agent and turns raw LangGraph stream chunks into simple events for the UI."""

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field

from langgraph.types import Command

from analyst.agent.events_text import message_text
from analyst.guardrails.suite import GuardrailBlocked, GuardrailSuite, OutputReport

logger = logging.getLogger(__name__)


@dataclass
class AgentEvent:
    kind: str  # todos | tool_call | tool_result | thought | file | interrupt | final | error | blocked
    agent: str = "analyst"  # analyst (main) or a subagent name
    name: str = ""  # tool name
    content: str = ""
    data: dict = field(default_factory=dict)


def describe_error(exc: Exception) -> str:
    """Turn provider errors into something a user can act on."""
    text = str(exc)
    if "429" in text or "rate limit" in text.lower() or type(exc).__name__ == "RateLimitError":
        scope = "daily token" if "per day" in text or "TPD" in text else "per-minute"
        return (
            f"The model provider's {scope} rate limit was reached. Pick another model in the "
            "sidebar (each has its own quota) or try again later."
        )
    if "api key" in text.lower() or "401" in text:
        return "The model provider rejected the API key. Check the key in the sidebar."
    return f"{type(exc).__name__}: {text[:400]}"


def _clip(text: str, n: int = 1500) -> str:
    return text if len(text) <= n else text[:n] + f"\n... [{len(text) - n} more characters]"


class AgentRunner:
    def __init__(self, agent, guards: GuardrailSuite, recursion_limit: int = 80):
        self.agent = agent
        self.guards = guards
        self.recursion_limit = recursion_limit
        self._agent_by_ns: dict[tuple, str] = {}
        self.tokens = 0  # total LLM tokens used by this runner (main agent + subagents)

    def config(self, thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}, "recursion_limit": self.recursion_limit}

    # ---- public API ----------------------------------------------------
    def ask(self, question: str, thread_id: str) -> Iterator[AgentEvent]:
        """Start a turn. Guards the input, then streams the agent's work."""
        try:
            question = self.guards.check_input(question)
        except GuardrailBlocked as exc:
            yield AgentEvent("blocked", content=f"Request blocked by guardrail: {exc.reason}")
            return
        yield from self._stream({"messages": [{"role": "user", "content": question}]}, thread_id)

    def resume(self, decision: dict, thread_id: str) -> Iterator[AgentEvent]:
        """Continue after a human decision on a paused tool call."""
        yield from self._stream(Command(resume={"decisions": [decision]}), thread_id)

    def pending_interrupt(self, thread_id: str) -> AgentEvent | None:
        state = self.agent.get_state(self.config(thread_id))
        for task in state.tasks:
            for interrupt in task.interrupts:
                return self._interrupt_event(interrupt)
        return None

    def state_values(self, thread_id: str) -> dict:
        return self.agent.get_state(self.config(thread_id)).values or {}

    # ---- streaming -----------------------------------------------------
    def _stream(self, payload, thread_id: str) -> Iterator[AgentEvent]:
        cfg = self.config(thread_id)
        try:
            for ns, mode, data in self.agent.stream(
                payload, cfg, stream_mode=["updates", "messages"], subgraphs=True
            ):
                if mode == "messages":
                    self._learn_agent_name(ns, data)
                    continue
                yield from self._updates(ns, data)
        except Exception as exc:
            logger.exception("agent run failed")
            yield AgentEvent("error", content=describe_error(exc))
            return

        paused = self.pending_interrupt(thread_id)
        if paused:
            yield paused
            return
        yield self._final(thread_id)

    def _learn_agent_name(self, ns: tuple, data) -> None:
        if not ns:
            return
        _, metadata = data
        name = metadata.get("lc_agent_name")
        if name:
            self._agent_by_ns[ns] = name

    def _label(self, ns: tuple) -> str:
        return self._agent_by_ns.get(ns, "analyst" if not ns else "subagent")

    def _updates(self, ns: tuple, chunk: dict) -> Iterator[AgentEvent]:
        agent = self._label(ns)
        for node, update in chunk.items():
            if node == "__interrupt__":
                yield self._interrupt_event(update[0])
                continue
            if not isinstance(update, dict):
                continue
            if update.get("todos"):
                yield AgentEvent("todos", agent, data={"todos": update["todos"]})
            for message in update.get("messages") or []:
                yield from self._message_events(agent, message)
            if update.get("files"):
                for path, file in update["files"].items():
                    yield AgentEvent("file", agent, name=path, data={"file": file})

    def _message_events(self, agent: str, message) -> Iterator[AgentEvent]:
        if message.type == "ai":
            usage = getattr(message, "usage_metadata", None) or {}
            self.tokens += int(usage.get("total_tokens", 0))
            for call in message.tool_calls or []:
                if call["name"] == "write_todos":
                    continue  # shown as a plan instead
                yield AgentEvent("tool_call", agent, call["name"], data={"args": call["args"]})
            text = message_text(message)
            if text.strip() and not message.tool_calls:
                yield AgentEvent("thought", agent, content=text)
        elif message.type == "tool":
            if message.name == "write_todos":
                return
            yield AgentEvent("tool_result", agent, message.name or "", _clip(message_text(message)))

    # ---- interrupts & final answer ------------------------------------
    @staticmethod
    def _interrupt_event(interrupt) -> AgentEvent:
        value = interrupt.value or {}
        request = (value.get("action_requests") or [{}])[0]
        return AgentEvent(
            "interrupt",
            name=request.get("name", ""),
            content=request.get("description", ""),
            data={"args": request.get("args", {})},
        )

    def _final(self, thread_id: str) -> AgentEvent:
        values = self.state_values(thread_id)
        raw = message_text(values["messages"][-1]) if values.get("messages") else ""
        report: OutputReport = self.guards.check_output(raw)
        files = {p: self._file_text(f) for p, f in (values.get("files") or {}).items()}
        if "/report.md" in files:  # the report is user-facing text too
            files["/report.md"] = self.guards.check_output(files["/report.md"]).text
        return AgentEvent(
            "final",
            content=report.text,
            data={"warnings": report.warnings, "files": files, "tokens": self.tokens},
        )

    @staticmethod
    def _file_text(file) -> str:
        content = file.get("content", "") if isinstance(file, dict) else str(file)
        return "\n".join(content) if isinstance(content, list) else str(content)
