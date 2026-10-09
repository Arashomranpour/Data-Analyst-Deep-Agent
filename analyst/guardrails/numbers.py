"""Number extraction + grounding. Used by the GroundedNumbers validator to catch figures in
an answer that never appeared in any query result (a common form of LLM hallucination)."""

import re
import threading
from dataclasses import dataclass

import numpy as np

_NUMBER = re.compile(
    r"(?<![\w.])(\$?)(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)\s?"
    r"(%|[kKmMbB](?![A-Za-z])|(?:thousand|million|billion)\b)?(?!\w)"
)
_SCALES = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "billion": 1e9}


@dataclass
class ParsedNumber:
    raw: str
    value: float
    scale: float
    decimals: int
    percent: bool


# Models often group digits with a (narrow) no-break or thin space: "165 438" -> 165438.
_GROUP_SPACE = re.compile(r"(?<=\d)[    ](?=\d{3}(?!\d))")


def extract_numbers(text: str) -> list[ParsedNumber]:
    """Numbers that make a factual claim. Small integers (<=10) and years are ignored."""
    text = _GROUP_SPACE.sub("", text)
    found = []
    for m in _NUMBER.finditer(text):
        _, digits, suffix = m.groups()
        decimals = len(digits.split(".")[1]) if "." in digits else 0
        number = float(digits.replace(",", ""))
        percent = suffix == "%"
        scale = _SCALES.get((suffix or "").lower(), 1.0) if not percent else 1.0
        plain_int = decimals == 0 and suffix is None and "," not in digits
        if plain_int and (number <= 10 or 1900 <= number <= 2100):
            continue
        found.append(ParsedNumber(m.group(0).strip(), number * scale, scale, decimals, percent))
    return found


class Evidence:
    """Every numeric value the agent has actually seen in query results (plus the user's own)."""

    def __init__(self) -> None:
        self._values: list[float] = []
        self._lock = threading.Lock()

    def add_values(self, values) -> None:
        arr = [
            float(v)
            for v in values
            if isinstance(v, (int, float, np.integer, np.floating))
            and not isinstance(v, bool)
            and v == v  # drop NaN
        ]
        with self._lock:
            self._values.extend(arr)

    def add_text(self, text: str) -> None:
        self.add_values(n.value for n in extract_numbers(text))
        self.add_values(float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", text) if x)

    def array(self) -> np.ndarray:
        with self._lock:
            return np.array(self._values, dtype=float)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()


def is_grounded(number: ParsedNumber, evidence: np.ndarray) -> bool:
    if evidence.size == 0:
        return False
    candidates = [evidence, evidence * 100] if number.percent else [evidence]
    tolerance = 0.005 * max(abs(number.value), 1e-9)  # 0.5 % relative
    for arr in candidates:
        if np.any(np.abs(arr - number.value) <= tolerance):
            return True
        # rounding: "$1.2M" is grounded by 1,234,567
        target = round(number.value / number.scale, number.decimals)
        if np.any(np.round(arr / number.scale, number.decimals) == target):
            return True
    return False


def ungrounded_numbers(text: str, evidence: np.ndarray) -> list[str]:
    return [n.raw for n in extract_numbers(text) if not is_grounded(n, evidence)]
