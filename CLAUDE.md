# Data Analyst Deep Agent

Streamlit app: upload CSVs, ask questions in English, a LangChain `deepagents` planner + 4 subagents
(`data-profiler`, `sql-analyst`, `visualizer`, `critic`) query a read-only SQLite store, chart and report.
Every input, SQL query, tool result and answer passes through custom Guardrails AI validators.
Single-user workbench; data lives in memory for the session.

## Commands
- Run (offline, no key): `LLM_BACKEND=fake streamlit run streamlit_app.py` (PowerShell: `$env:LLM_BACKEND="fake"` first)
- Run (real): set `GROQ_API_KEY` in `.env`, then `streamlit run streamlit_app.py`
- Test: `pytest -q` (158 tests, offline, ~25 s) · Lint: `ruff check .` (line length 110, py312)
- CI runs `ruff check .` then `pytest -q` with `LLM_BACKEND=fake OTEL_SDK_DISABLED=true`

## Layout
`streamlit_app.py` UI entry · `analyst/config.py` Settings · `analyst/data/` DataStore + sample data ·
`analyst/guardrails/` validators, suite, numbers, events · `analyst/tools/` toolkit + artifacts ·
`analyst/agent/` builder, prompts, runner, fake_model · `analyst/ui/` session + views · `analyst/export/` report builders · `analyst/persistence.py` save/restore · `analyst/auth/users.py` accounts · `analyst/tools/stats.py` statistics · `scripts/deploy_hf.py` Hugging Face deploy · `tests/`.
Knowledge graph of the code: `graphify-out/GRAPH_REPORT.md` (query with `/graphify query "..."`).

## Non-negotiables
- Defence in depth: guardrails are NOT the only protection. The DB stays read-only (SQLite authorizer),
  row-capped and time-limited. Never weaken the store to "make a guard pass".
- No `exec`/`eval` of model-written code. Charts come from the structured `make_chart` tool.
- Tests run offline using the scripted fake model. Never call a real LLM from tests.
- Bring your own key: the host `GROQ_API_KEY` is ignored unless `ALLOW_SERVER_KEY=true`; never persist, log or display a user's key (last 4 chars at most).
- Never commit `.env`, API keys, `.sessions/` or `.data/` (user DB).
- Auth: never store or log plaintext passwords; sign-in errors stay generic; per-user paths come only from validated usernames.
- Exported HTML must escape model/data text (report builder does); persistence is plain JSON, never pickle.
- Use Python 3.12 (guardrails-ai does not install on 3.14): `uv venv --python 3.12 .venv`.

## Detailed guidance (loaded on demand)
- Rules in `.claude/rules/` (path-scoped): python-style, guardrails, agent, data-and-tools, testing.
- Skills in `.claude/skills/`: `verify` (lint + tests), `add-validator`, `red-team`.
