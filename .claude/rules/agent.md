---
paths:
  - "analyst/agent/**"
  - "analyst/ui/**"
  - "streamlit_app.py"
---
# Agent and UI
- `builder.py` builds the deep agent (`create_deep_agent`): planner + 4 subagents, optional human-in-the-loop
  approval on SQL. Prompts live in `prompts.py`; edit them there, not inline.
- `runner.py` streams LangGraph chunks into clean `AgentEvent`s; the UI consumes only those events.
- `fake_model.py` (`ScriptedAnalystModel`) walks plan -> SQL -> chart -> report offline. If you add a tool or a
  step to the agent flow, update the script so offline runs and tests still pass.
- Provider errors become user-actionable messages (`describe_error`); fail fast on rate limits.
- UI state belongs in `AnalystSession` (`ui/session.py`); `ui/views.py` stays presentation-only.
