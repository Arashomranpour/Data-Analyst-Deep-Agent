import threading
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

STATUSES = ("passed", "fixed", "blocked", "warning")


@dataclass
class GuardrailEvent:
    stage: str  # input | sql | tool_output | output
    validator: str
    status: str  # passed | fixed | blocked | warning
    detail: str = ""
    ts: str = field(default_factory=lambda: datetime.now(UTC).strftime("%H:%M:%S"))

    def as_dict(self) -> dict:
        return asdict(self)


class EventLog:
    """Thread-safe record of every guardrail decision (agent tools run in worker threads)."""

    def __init__(self) -> None:
        self._events: list[GuardrailEvent] = []
        self._lock = threading.Lock()

    def add(self, stage: str, validator: str, status: str, detail: str = "") -> None:
        with self._lock:
            self._events.append(GuardrailEvent(stage, validator, status, detail))

    def snapshot(self) -> list[GuardrailEvent]:
        with self._lock:
            return list(self._events)

    def counts(self) -> dict[str, int]:
        counter = Counter(e.status for e in self.snapshot())
        return {s: counter.get(s, 0) for s in STATUSES}

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
