"""Custom Guardrails AI validators.

Each one subclasses `guardrails.Validator`, so it plugs into a `Guard` and supports the
standard on-fail actions (EXCEPTION = block, FIX = repair, NOOP = flag only).
"""

import re

import sqlglot
from guardrails import Validator, register_validator
from guardrails.validator_base import FailResult, PassResult
from sqlglot import exp
from sqlglot.errors import SqlglotError

from analyst.guardrails.numbers import ungrounded_numbers

# --------------------------------------------------------------------------- injection
_INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+|any\s+|the\s+|your\s+)?(?:previous|prior|above|earlier)\s+(?:instructions?|prompts?|rules)",
    r"disregard\s+(?:all\s+|any\s+|the\s+|your\s+)?(?:previous|prior|above|earlier|rules|instructions?)",
    r"(?:reveal|show|print|repeat|leak)\s+(?:me\s+)?(?:your|the)\s+(?:system\s+|hidden\s+|initial\s+)?(?:prompt|instructions?)",
    r"you\s+are\s+now\s+(?:an?\s+)?",
    r"\bnew\s+instructions?\s*:",
    r"\bact\s+as\s+(?:an?\s+)?(?:unrestricted|jailbroken|different|evil)",
    r"\b(?:dan\s+mode|jailbreak|developer\s+mode)\b",
    r"<\|?(?:im_start|im_end|system|endoftext)\|?>",
    r"\bdrop\s+(?:the\s+)?\w*\s*table\b",
    r"(?:email|send|forward|exfiltrate)\s+(?:all\s+|the\s+)?(?:customer|user|private|sensitive)\s+(?:data|information|records)",
]
_INJECTION_RE = re.compile("|".join(f"(?:{p})" for p in _INJECTION_PATTERNS), re.IGNORECASE)
# Expand a match to the whole table cell / line so no instruction fragment survives.
_INJECTION_SEGMENT_RE = re.compile(rf"[^|\n]*?(?:{_INJECTION_RE.pattern})[^|\n]*", re.IGNORECASE)
INJECTION_PLACEHOLDER = "[removed: possible prompt injection]"


def find_injection(text: str) -> list[str]:
    return [m.group(0).strip() for m in _INJECTION_RE.finditer(text)]


@register_validator(name="analyst/prompt_injection", data_type="string")
class PromptInjection(Validator):
    """Detects instruction-hijacking text. FIX replaces the whole offending cell/line."""

    def _validate(self, value, metadata=None):
        hits = find_injection(value)
        if not hits:
            return PassResult()
        fixed = _INJECTION_SEGMENT_RE.sub(INJECTION_PLACEHOLDER, value)
        return FailResult(
            error_message=f"Possible prompt injection ({len(hits)} match): '{hits[0][:60]}'",
            fix_value=fixed,
        )


# --------------------------------------------------------------------------------- SQL
_FORBIDDEN_NODE_NAMES = (
    "Insert",
    "Update",
    "Delete",
    "Create",
    "Drop",
    "Alter",
    "Command",
    "Pragma",
    "Attach",
    "Detach",
    "Merge",
    "Transaction",
    "Commit",
    "Rollback",
)
_FORBIDDEN_NODES = tuple(getattr(exp, n) for n in _FORBIDDEN_NODE_NAMES if hasattr(exp, n))
_FORBIDDEN_FUNCTIONS = {"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer"}


def check_sql(sql: str, allowed_tables: set[str]) -> str | None:
    """Return a reason the query is unsafe, or None if it is a safe single SELECT."""
    if not sql or not sql.strip():
        return "Empty query."
    try:
        statements = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except SqlglotError as exc:
        return f"Could not parse SQL: {str(exc)[:120]}"
    if len(statements) != 1:
        return "Only a single SQL statement is allowed."
    root = statements[0]
    if not isinstance(root, exp.Query):
        return f"Only read-only SELECT queries are allowed (got {type(root).__name__.upper()})."
    if root.find(*_FORBIDDEN_NODES):
        return "Data-changing or administrative statements are not allowed."
    for func in root.find_all(exp.Func):
        name = (func.name if isinstance(func, exp.Anonymous) else func.sql_name()).lower()
        if name in _FORBIDDEN_FUNCTIONS:
            return f"Function '{name}' is not allowed."
    cte_names = {c.alias_or_name.lower() for c in root.find_all(exp.CTE)}
    for table in root.find_all(exp.Table):
        name = table.name.lower()
        if name not in allowed_tables and name not in cte_names:
            return f"Unknown table '{table.name}'. Available: {sorted(allowed_tables)}."
    return None


@register_validator(name="analyst/safe_sql", data_type="string")
class SafeSQL(Validator):
    """Blocks anything except a single read-only SELECT over the loaded tables."""

    def _validate(self, value, metadata=None):
        allowed = {t.lower() for t in (metadata or {}).get("allowed_tables", [])}
        problem = check_sql(value, allowed)
        return FailResult(error_message=problem) if problem else PassResult()


@register_validator(name="analyst/enforce_limit", data_type="string")
class EnforceLimit(Validator):
    """Adds a row cap to queries that have none (a FIX, not a block)."""

    def _validate(self, value, metadata=None):
        max_rows = int((metadata or {}).get("max_rows", 200))
        try:
            root = sqlglot.parse_one(value, read="sqlite")
        except SqlglotError:
            return PassResult()  # SafeSQL already reports unparsable queries
        if root.args.get("limit") is not None:
            return PassResult()
        wrapped = f"SELECT * FROM ({value.strip().rstrip(';')}) LIMIT {max_rows}"
        return FailResult(error_message=f"No LIMIT clause; capped at {max_rows} rows.", fix_value=wrapped)


# ---------------------------------------------------------------------------------- PII
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+\d{1,3}[ .-])?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)")
_SSN_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")


def _luhn_ok(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    return total % 10 == 0


def redact_pii(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}

    def sub(pattern, label, check=None):
        nonlocal text

        def repl(m):
            if check and not check(m.group(0)):
                return m.group(0)
            counts[label] = counts.get(label, 0) + 1
            return f"[{label}]"

        text = pattern.sub(repl, text)

    sub(_EMAIL_RE, "EMAIL")
    sub(_SSN_RE, "SSN")
    sub(_CARD_RE, "CARD", _luhn_ok)
    sub(_PHONE_RE, "PHONE")
    return text, counts


@register_validator(name="analyst/pii", data_type="string")
class PIIRedactor(Validator):
    """Masks emails, phone numbers, SSNs and (Luhn-valid) card numbers."""

    def _validate(self, value, metadata=None):
        redacted, counts = redact_pii(value)
        if not counts:
            return PassResult()
        summary = ", ".join(f"{n} {k.lower()}" for k, n in counts.items())
        return FailResult(error_message=f"PII redacted: {summary}", fix_value=redacted)


# ------------------------------------------------------------------------ grounding
@register_validator(name="analyst/grounded_numbers", data_type="string")
class GroundedNumbers(Validator):
    """Flags figures in an answer that do not appear in any query result.

    `metadata["evidence"]` is a numpy array of every number the agent actually saw.
    """

    def _validate(self, value, metadata=None):
        evidence = (metadata or {}).get("evidence")
        if evidence is None:
            return PassResult()
        missing = ungrounded_numbers(value, evidence)
        if not missing:
            return PassResult()
        shown = ", ".join(dict.fromkeys(missing))
        return FailResult(error_message=f"Numbers not found in any query result: {shown}")
