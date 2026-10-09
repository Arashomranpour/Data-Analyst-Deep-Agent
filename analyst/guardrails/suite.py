"""The guardrail pipeline: which Guardrails AI `Guard` runs at which point of the agent loop.

    user input ──► [input guard]  ──► agent ──► tool call (SQL) ──► [SQL guard] ──► database
                                       ▲                                              │
                                       └─ [tool-output guard] ◄── query result ───────┘
    agent answer ──► [output guard] ──► user

Every decision is appended to an EventLog so the UI can show exactly what was blocked,
repaired or flagged.
"""

from dataclasses import dataclass, field

from guardrails import Guard, OnFailAction
from guardrails.errors import ValidationError

from analyst.guardrails.events import EventLog
from analyst.guardrails.numbers import Evidence
from analyst.guardrails.validators import (
    EnforceLimit,
    GroundedNumbers,
    PIIRedactor,
    PromptInjection,
    SafeSQL,
)


class GuardrailBlocked(Exception):
    """Raised when a guard refuses the input / action. The message is safe to show the user."""

    def __init__(self, validator: str, reason: str):
        super().__init__(reason)
        self.validator = validator
        self.reason = reason


@dataclass
class OutputReport:
    text: str
    warnings: list[str] = field(default_factory=list)


class GuardrailSuite:
    def __init__(self, events: EventLog, evidence: Evidence, enabled: bool = True):
        self.events = events
        self.evidence = evidence
        self.enabled = enabled

        self._input = Guard(name="input").use(PromptInjection(on_fail=OnFailAction.EXCEPTION))
        self._sql = Guard(name="sql").use(
            SafeSQL(on_fail=OnFailAction.EXCEPTION),
            EnforceLimit(on_fail=OnFailAction.FIX),
        )
        self._tool_output = Guard(name="tool_output").use(
            PromptInjection(on_fail=OnFailAction.FIX),
            PIIRedactor(on_fail=OnFailAction.FIX),
        )
        self._output = Guard(name="output").use(
            PIIRedactor(on_fail=OnFailAction.FIX),
            GroundedNumbers(on_fail=OnFailAction.NOOP),
        )

    # ---- helpers -------------------------------------------------------
    def _log_summaries(self, stage: str, outcome, fix_actions: set[str]) -> None:
        for s in outcome.validation_summaries:
            if s.validator_status == "pass":
                self.events.add(stage, s.validator_name, "passed")
            else:
                status = "fixed" if s.validator_name in fix_actions else "warning"
                self.events.add(stage, s.validator_name, status, s.failure_reason or "")

    # ---- guards --------------------------------------------------------
    def check_input(self, text: str) -> str:
        """Block prompt-injection attempts typed by the user."""
        if not self.enabled:
            return text
        try:
            self._input.validate(text)
        except ValidationError as exc:
            reason = str(exc).split("errors:", 1)[-1].strip()
            self.events.add("input", "PromptInjection", "blocked", reason)
            raise GuardrailBlocked("PromptInjection", reason) from exc
        self.events.add("input", "PromptInjection", "passed")
        return text

    def check_sql(self, sql: str, allowed_tables: list[str], max_rows: int) -> str:
        """Allow only a single read-only SELECT; add a row cap if missing."""
        if not self.enabled:
            return sql
        try:
            outcome = self._sql.validate(
                sql, metadata={"allowed_tables": allowed_tables, "max_rows": max_rows}
            )
        except ValidationError as exc:
            reason = str(exc).split("errors:", 1)[-1].strip()
            self.events.add("sql", "SafeSQL", "blocked", f"{reason} | {sql[:120]}")
            raise GuardrailBlocked("SafeSQL", reason) from exc
        self._log_summaries("sql", outcome, fix_actions={"EnforceLimit"})
        return outcome.validated_output

    def sanitize_tool_output(self, text: str) -> str:
        """Neutralise injected instructions and PII inside data returned to the model."""
        if not self.enabled:
            return text
        outcome = self._tool_output.validate(text)
        self._log_summaries("tool_output", outcome, fix_actions={"PromptInjection", "PIIRedactor"})
        return outcome.validated_output

    def check_output(self, text: str) -> OutputReport:
        """Redact PII and flag numbers that are not backed by any query result."""
        if not self.enabled:
            return OutputReport(text)
        outcome = self._output.validate(text, metadata={"evidence": self.evidence.array()})
        self._log_summaries("output", outcome, fix_actions={"PIIRedactor"})
        warnings = [
            s.failure_reason
            for s in outcome.validation_summaries
            if s.validator_name == "GroundedNumbers" and s.validator_status != "pass"
        ]
        return OutputReport(outcome.validated_output, [w for w in warnings if w])
