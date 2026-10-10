# Graph Report - data-analyst-deep-agent  (2026-10-10)

## Corpus Check
- Corpus is ~38,495 words - fits in a single context window. You may not need a graph.

## Summary
- 524 nodes · 1218 edges · 27 communities (19 shown, 8 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 152 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Settings & Persistence
- Report Export
- Sample Data & SQL Store
- Agent Builder & Model
- Agent Runner & Events
- Number Grounding
- Live Progress
- Injection Classifiers
- Guardrail Suite & Validators
- Event Log & Evidence
- README & Tech Stack
- Data/Tools Rules
- Streamlit UI Tests
- Toolkit Module
- CLAUDE.md & Style Rules
- Red-team & Sample Data Docs
- Agent/UI Rules
- Guardrails Rule & Audit
- CI Workflow
- Guardrail Blocking
- Agent Tools

## God Nodes (most connected - your core abstractions)
1. `AnalystSession` - 36 edges
2. `EventLog` - 31 edges
3. `AgentEvent` - 29 edges
4. `GuardrailSuite` - 29 edges
5. `RunProgress` - 27 edges
6. `AgentRunner` - 24 edges
7. `Evidence` - 22 edges
8. `DataStore` - 20 edges
9. `load_session()` - 19 edges
10. `Settings` - 18 edges

## Surprising Connections (you probably didn't know these)
- `Plan & trace tab: todo list and tool-call trace (list_tables, run_sql, make_chart)` --references--> `make_chart structured tool (no exec)`  [INFERRED]
  docs/screenshot.png → README.md
- `Env` --uses--> `AgentRunner`  [INFERRED]
  tests/conftest.py → analyst/agent/runner.py
- `Env` --uses--> `Settings`  [INFERRED]
  tests/conftest.py → analyst/config.py
- `Env` --uses--> `DataStore`  [INFERRED]
  tests/conftest.py → analyst/data/store.py
- `Env` --uses--> `EventLog`  [INFERRED]
  tests/conftest.py → analyst/guardrails/events.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **CI flow: install dev deps, lint, test offline** — github_workflows_ci_ci_workflow, github_workflows_ci_ruff_step, github_workflows_ci_pytest_step [EXTRACTED 1.00]
- **Guardrails AI validators wired at checkpoints** — readme_prompt_injection_validator, readme_safesql_validator, readme_piiredactor_validator [EXTRACTED 1.00]
- **Offline fake-model testing flow** — readme_fake_backend, claude_rules_agent_fake_model, claude_rules_testing_offline [INFERRED 0.85]
- **Red-team workflow across skill, tests and sample data** — claude_skills_red_team_skill, claude_rules_testing_paired_redteam, claude_rules_data_and_tools_sample [INFERRED 0.85]

## Communities (27 total, 8 thin omitted)

### Community 0 - "Settings & Persistence"
Cohesion: 0.08
Nodes (32): get_settings(), _frame_from_json(), _frame_to_json(), list_sessions(), load_session(), save_session(), _slug(), AnalystSession (+24 more)

### Community 1 - "Report Export"
Cohesion: 0.08
Nodes (18): build_html(), build_markdown(), _guardrail_lines(), _stamp(), GuardrailEvent, Artifacts, ChartRecord, QueryRecord (+10 more)

### Community 2 - "Sample Data & SQL Store"
Cohesion: 0.06
Nodes (13): sample_sales_df(), _authorizer(), DataStore, _fmt(), QueryError, QueryResult, sanitize_table_name(), _sql_type() (+5 more)

### Community 3 - "Agent Builder & Model"
Cohesion: 0.07
Nodes (6): build_agent(), build_model(), ScriptedAnalystModel, tool_args_json(), Settings, Toolkit

### Community 4 - "Agent Runner & Events"
Cohesion: 0.08
Nodes (9): message_text(), AgentRunner, _clip(), describe_error(), OutputReport, kinds(), test_full_run_plans_queries_charts_reports_and_answers(), test_prompt_injection_in_the_question_is_blocked_before_the_agent_runs() (+1 more)

### Community 5 - "Number Grounding"
Cohesion: 0.09
Nodes (22): extract_numbers(), is_grounded(), ParsedNumber, ungrounded_numbers(), check_sql(), find_injection(), _luhn_ok(), redact_pii() (+14 more)

### Community 6 - "Live Progress"
Cohesion: 0.15
Nodes (17): AgentEvent, RunProgress, Stage, stage_for(), StageState, progress_html(), call(), Clock (+9 more)

### Community 7 - "Injection Classifiers"
Cohesion: 0.14
Nodes (15): available_classifiers(), get_classifier(), HeuristicClassifier, InjectionClassifier, register_classifier(), Verdict, scan_injection(), test_a_custom_classifier_can_be_registered_and_used() (+7 more)

### Community 8 - "Guardrail Suite & Validators"
Cohesion: 0.13
Nodes (6): injection(), EnforceLimit, GroundedNumbers, PIIRedactor, PromptInjection, SafeSQL

### Community 9 - "Event Log & Evidence"
Cohesion: 0.19
Nodes (6): EventLog, Evidence, GuardrailSuite, test_suite_default_detector_lets_the_paraphrase_through_control(), test_suite_with_heuristic_detector_blocks_a_paraphrased_attack(), test_tool_output_with_paraphrased_poison_is_repaired()

### Community 10 - "README & Tech Stack"
Cohesion: 0.15
Nodes (15): Python 3.12 requirement, README, Data Analyst Deep Agent, deepagents planner (write_todos), Groq LLM provider, Report export (Markdown/HTML), Session save/restore, Subagents (data-profiler, sql-analyst, visualizer, critic) (+7 more)

### Community 11 - "Data/Tools Rules"
Cohesion: 0.15
Nodes (13): Data store and tools rule, Artifacts (charts, /report.md), DataStore read-only SQLite, Evidence (feeds GroundedNumbers), Toolkit (list_tables, describe_table, run_sql, make_chart), Streamlit app screenshot (full analysis run), Chat panel with user request and agent answer, Plan & trace tab: todo list and tool-call trace (list_tables, run_sql, make_chart) (+5 more)

### Community 12 - "Streamlit UI Tests"
Cohesion: 0.22
Nodes (10): app(), button(), messages(), test_ask_a_question_end_to_end(), test_attack_prompt_is_blocked_and_logged(), test_chat_is_disabled_until_data_is_loaded(), test_exports_are_offered_after_a_run(), test_guardrails_toggle_changes_state() (+2 more)

### Community 14 - "CLAUDE.md & Style Rules"
Cohesion: 0.24
Nodes (12): CLAUDE.md project instructions, Project commands (run/test/lint/CI), Code layout, Red-team tests plus unguarded control policy, Python style rule, ruff config (E,F,I,B,UP; line 110), Testing rule, env / env_unguarded fixtures (Env) (+4 more)

### Community 15 - "Red-team & Sample Data Docs"
Cohesion: 0.21
Nodes (11): sample.py booby-trapped dataset, On-fail policy in suite.py, red-team skill, Booby-trapped sample dataset, EnforceLimit validator, Guardrail pipeline (4 checkpoints), Guardrails on-fail actions (EXCEPTION/FIX/NOOP), PIIRedactor validator (+3 more)

### Community 16 - "Agent/UI Rules"
Cohesion: 0.18
Nodes (11): Agent and UI rule, AnalystSession UI state, builder.py (create_deep_agent), describe_error provider error messages, ScriptedAnalystModel (fake_model.py), runner.py AgentEvent streaming, Config only via Settings, Configuration variables (+3 more)

### Community 17 - "Guardrails Rule & Audit"
Cohesion: 0.29
Nodes (8): Guardrails rule, EventLog thread-safe decision log, _INJECTION_PATTERNS, Pluggable injection detection (classifiers.py), Validator conventions (register_validator, Pass/FailResult), Guardrail audit log, Pluggable injection classifiers, PromptInjection validator

### Community 18 - "CI Workflow"
Cohesion: 0.38
Nodes (7): CI workflow (GitHub Actions), pytest step (LLM_BACKEND=fake), ruff check step, Offline test suite (110 tests), Dev dependencies, pytest, ruff

### Community 20 - "Agent Tools"
Cohesion: 0.53
Nodes (5): build_toolkit(), describe_table(), list_tables(), run_sql(), seen()

## Knowledge Gaps
- **16 isolated node(s):** `Sidebar: Guardrails AI enabled toggle (Protected)`, `Sidebar: Try a prompt buttons (Full analysis, Quick question, New conversation)`, `Chat panel with user request and agent answer`, `README`, `EnforceLimit validator` (+11 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 164 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Guardrails rule` connect `Guardrails Rule & Audit` to `Guardrail Suite & Validators`, `CLAUDE.md & Style Rules`, `Red-team & Sample Data Docs`?**
  _High betweenness centrality (0.257) - this node is a cross-community bridge._
- **Are the 21 inferred relationships involving `AnalystSession` (e.g. with `load_session()` and `save_session()`) actually correct?**
  _`AnalystSession` has 21 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Sidebar: Guardrails AI enabled toggle (Protected)`, `Sidebar: Try a prompt buttons (Full analysis, Quick question, New conversation)`, `Chat panel with user request and agent answer` to the rest of the system?**
  _16 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Settings & Persistence` be split into smaller, more focused modules?**
  _Cohesion score 0.07539682539682539 - nodes in this community are weakly interconnected._
- **Why does `CLAUDE.md project instructions` connect `CLAUDE.md & Style Rules` to `README & Tech Stack`, `Data/Tools Rules`, `Red-team & Sample Data Docs`, `Agent/UI Rules`, `Guardrails Rule & Audit`?**
  _High betweenness centrality (0.194) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `EventLog` (e.g. with `build_html()` and `build_markdown()`) actually correct?**
  _`EventLog` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Should `Report Export` be split into smaller, more focused modules?**
  _Cohesion score 0.07609427609427609 - nodes in this community are weakly interconnected._