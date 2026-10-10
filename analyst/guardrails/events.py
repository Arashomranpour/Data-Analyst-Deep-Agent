import csv
import io
import json
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
    at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))

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

    # ---- audit export --------------------------------------------------
    def summary(self) -> dict:
        """Counts overall, per stage and per validator - the header of an audit file."""
        events = self.snapshot()
        by_validator: dict[str, dict[str, int]] = {}
        by_stage: dict[str, dict[str, int]] = {}
        for e in events:
            for bucket, key in ((by_validator, e.validator), (by_stage, e.stage)):
                row = bucket.setdefault(key, dict.fromkeys(STATUSES, 0))
                row[e.status] = row.get(e.status, 0) + 1
        return {
            "total": len(events),
            "by_status": self.counts(),
            "by_stage": by_stage,
            "by_validator": by_validator,
        }

    def to_json(self) -> str:
        return json.dumps(
            {"summary": self.summary(), "events": [e.as_dict() for e in self.snapshot()]}, indent=2
        )

    def to_csv(self) -> str:
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=["at", "ts", "stage", "validator", "status", "detail"])
        writer.writeheader()
        for e in self.snapshot():
            writer.writerow(e.as_dict())
        return out.getvalue()

    def load(self, rows: list[dict]) -> None:
        """Replace the log with previously exported events (used when restoring a saved session)."""
        events = [
            GuardrailEvent(**{k: v for k, v in r.items() if k in GuardrailEvent.__dataclass_fields__})
            for r in rows
        ]
        with self._lock:
            self._events[:] = events

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
