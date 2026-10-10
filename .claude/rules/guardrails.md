---
paths:
  - "analyst/guardrails/**"
---
# Guardrails
- Validators subclass `guardrails.Validator`, use `@register_validator(name="analyst/<name>")`, and return
  `PassResult` / `FailResult` (with `fix_value` when repairable). Keep them deterministic and dependency-light.
- On-fail policy lives in `suite.py` only: EXCEPTION = block, FIX = repair, NOOP = flag.
  Current wiring: input -> PromptInjection (block); sql -> SafeSQL (block) + EnforceLimit (fix);
  tool_output -> PromptInjection (fix) + PIIRedactor (fix); output -> PIIRedactor (fix) + GroundedNumbers (flag).
- Every decision is logged to the thread-safe `EventLog` so the UI Guardrails tab shows it.
- `SafeSQL` parses with `sqlglot`: one read-only SELECT/WITH, known tables only, no dangerous functions.
- `GroundedNumbers` is a heuristic and must warn, not block. Injection detection is regex-based; extend
  `_INJECTION_PATTERNS` rather than adding ad-hoc checks elsewhere.
- Any new pattern or validator needs red-team tests in `tests/test_validators.py`, plus a control showing the
  attack succeeds with guardrails off.
- Injection detection is pluggable: `PromptInjection(detector=...)` -> `scan_injection` -> classifiers registered in `classifiers.py`. Heuristic/custom classifiers must stay offline-testable and need benign-text tests (no false positives on analyst questions).
