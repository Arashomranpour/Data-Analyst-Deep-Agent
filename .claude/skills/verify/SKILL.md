---
name: verify
description: Run lint and the offline test suite for this project and report real results. Use before claiming a change is done, before committing, or when asked to check, test or lint.
---
# Verify

1. `ruff check .` - report any findings (do not silence rules).
2. Run the tests offline with the fake model:
   - bash: `LLM_BACKEND=fake OTEL_SDK_DISABLED=true pytest -q`
   - PowerShell: `$env:LLM_BACKEND="fake"; $env:OTEL_SDK_DISABLED="true"; pytest -q`
3. Report pass/fail counts verbatim (about 110 tests expected). If anything fails, show the failing test and its
   output; do not claim success. This mirrors `.github/workflows/ci.yml`.
