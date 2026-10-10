---
paths:
  - "tests/**"
---
# Testing
- All tests are offline: `Settings(llm_backend="fake")`. Use the `env` / `env_unguarded` fixtures from
  `conftest.py` (`Env` wires store + guards + tools + runner).
- Layout: validators (`test_validators.py`), store/tools (`test_store_and_tools.py`), real deep-agent graph with
  the scripted model (`test_agent.py`), headless Streamlit (`test_ui.py`, `streamlit.testing.v1`).
- Red-team tests come in pairs: blocked/repaired with guardrails on, succeeds with guardrails off.
- Keep the suite fast (~15 s): no network, no sleeps.
