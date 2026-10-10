"""Pluggable prompt-injection classifiers.

The regex list in `validators.py` is fast and explainable but only catches phrasings it knows.
A classifier scores text in [0, 1] and says *why*, so a stronger detector (for example a
model-based one) can be registered without touching the validator or the suite:

    register_classifier("my_model", lambda: MyModelClassifier())
    Settings(injection_detector="my_model")

Built-ins: `heuristic` (offline weighted signals). `regex` / `both` are handled by the validator.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Verdict:
    score: float  # 0 = clean, 1 = certainly an injection
    signals: tuple[str, ...] = field(default_factory=tuple)


class InjectionClassifier(Protocol):
    def analyse(self, text: str) -> Verdict: ...


_REGISTRY: dict[str, Callable[[], InjectionClassifier]] = {}


def register_classifier(name: str, factory: Callable[[], InjectionClassifier]) -> None:
    _REGISTRY[name] = factory


def get_classifier(name: str) -> InjectionClassifier:
    if name not in _REGISTRY:
        raise ValueError(f"Unknown injection classifier '{name}'. Registered: {sorted(_REGISTRY)}")
    return _REGISTRY[name]()


def available_classifiers() -> list[str]:
    return sorted(_REGISTRY)


# ------------------------------------------------------------------------------ heuristic
_I = re.IGNORECASE
_SENSITIVE = r"(?:customers?|users?|clients?|employees?|records?|data|database|credentials?|passwords?|api\s*keys?|secrets?|tokens?)"
_SIGNALS: tuple[tuple[str, float, re.Pattern], ...] = (
    (
        "override-instructions",
        0.6,
        re.compile(
            r"\b(?:ignore|disregard|forget|override|bypass|discard|skip)\b(?:\W+\w+){0,5}?\W+"
            r"(?:instructions?|rules?|guidelines?|polic(?:y|ies)|prompts?|restrictions?|safeguards?|"
            r"everything|anything)\b",
            _I,
        ),
    ),
    (
        "forget-context",
        0.6,
        re.compile(
            r"\b(?:forget|disregard|ignore)\b\W+(?:everything|all|what)\b(?:\W+\w+){0,4}?\W+"
            r"(?:told|said|above|before|earlier|learned|instructed)\b",
            _I,
        ),
    ),
    (
        "reveal-prompt",
        0.6,
        re.compile(
            r"\b(?:reveal|show|print|repeat|output|leak|tell\s+me|disclose|display)\b(?:\W+\w+){0,4}?\W+"
            r"(?:system\s+prompt|hidden\s+(?:prompt|instructions?)|initial\s+(?:prompt|instructions?)|"
            r"your\s+(?:instructions?|prompt|rules))",
            _I,
        ),
    ),
    (
        "persona-switch",
        0.45,
        re.compile(
            r"\b(?:pretend\s+(?:to\s+be|you\s+are)|from\s+now\s+on,?\s+you|you\s+are\s+now|"
            r"act\s+as\s+(?:if|though|an?\s+(?:different|new|unrestricted)))",
            _I,
        ),
    ),
    (
        "exfiltrate-data",
        0.5,
        re.compile(
            rf"\b(?:send|email|mail|forward|post|upload|exfiltrate|transmit|leak)\b(?:\W+\w+){{0,4}}?\W+"
            rf"(?:all|every|the|their|these)?\W*{_SENSITIVE}\b",
            _I,
        ),
    ),
    (
        "external-recipient",
        0.4,
        re.compile(
            r"\b(?:send|email|mail|forward|post|upload|transmit)\b[^.\n]{0,80}?"
            r"(?:\bto\b|\bat\b)\W+(?:[\w.+-]+@[\w-]+\.[\w.-]+|https?://\S+)",
            _I,
        ),
    ),
    (
        "addresses-the-assistant",
        0.35,
        re.compile(
            r"\b(?:attention\s+(?:ai|assistant|agent|model)|(?:ai|assistant|agent|llm)\s*[:,]\s*(?:you|please|now)|"
            r"as\s+(?:the|an?)\s+(?:ai|assistant|agent)\s*,?\s*you\s+(?:must|should|will))",
            _I,
        ),
    ),
    (
        "fake-role-header",
        0.5,
        re.compile(r"(?m)^\s*(?:#{1,3}\s*)?(?:system|assistant|developer)\s*(?:prompt|message)?\s*:", _I),
    ),
    ("chat-template-token", 0.6, re.compile(r"<\|?(?:im_start|im_end|system|endoftext)\|?>|\[/?INST\]", _I)),
    ("encoded-payload", 0.3, re.compile(r"[A-Za-z0-9+/]{48,}={0,2}")),
)


class HeuristicClassifier:
    """Offline weighted-signal scorer. Independent signals combine as 1 - prod(1 - weight), so one
    weak hint stays below the default 0.7 threshold but two corroborating hints cross it."""

    def analyse(self, text: str) -> Verdict:
        hits = [(name, weight) for name, weight, pattern in _SIGNALS if pattern.search(text)]
        remaining = 1.0
        for _, weight in hits:
            remaining *= 1.0 - weight
        return Verdict(round(1.0 - remaining, 3), tuple(name for name, _ in hits))


register_classifier("heuristic", HeuristicClassifier)
