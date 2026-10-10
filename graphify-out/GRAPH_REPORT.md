# Graph Report - data-analyst-deep-agent  (2026-10-10)

## Corpus Check
- Corpus is ~32,566 words - fits in a single context window. You may not need a graph.

## Summary
- 358 nodes · 728 edges · 16 communities (10 shown, 6 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 90 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Agent Builder & Architecture
- UI Screenshot & CI
- SQL DataStore
- Number Grounding
- Guardrail Suite
- Sample Data & Event Log
- Session & Settings
- Agent Runner
- Scripted Fake Model
- Agent Tests & Errors
- Streamlit UI Tests

## God Nodes (most connected - your core abstractions)
1. `GuardrailSuite` - 25 edges
2. `AnalystSession` - 25 edges
3. `AgentRunner` - 24 edges
4. `DataStore` - 19 edges
5. `Evidence` - 18 edges
6. `build_toolkit()` - 18 edges
7. `Artifacts` - 17 edges
8. `AgentEvent` - 16 edges
9. `EventLog` - 16 edges
10. `Env` - 15 edges

## Surprising Connections (you probably didn't know these)
- `Sidebar: Guardrails AI enabled toggle (Protected)` --references--> `Guardrails AI`  [INFERRED]
  docs/screenshot.png → README.md
- `Plan & trace tab: todo list and tool-call trace (list_tables, run_sql, make_chart)` --references--> `Deep agent planner (deepagents, write_todos)`  [INFERRED]
  docs/screenshot.png → README.md
- `Plan & trace tab: todo list and tool-call trace (list_tables, run_sql, make_chart)` --references--> `make_chart structured tool (no exec)`  [INFERRED]
  docs/screenshot.png → README.md
- `Plan & trace tab: todo list and tool-call trace (list_tables, run_sql, make_chart)` --references--> `Agent tools: list_tables, describe_table, run_sql`  [INFERRED]
  docs/screenshot.png → README.md
- `Sidebar: Try a prompt buttons (Full analysis, Quick question, New conversation)` --conceptually_related_to--> `Booby-trapped sample dataset`  [INFERRED]
  docs/screenshot.png → README.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Custom Guardrails AI validators across pipeline checkpoints** — readme_prompt_injection_validator, readme_safe_sql_validator, readme_enforce_limit_validator, readme_pii_redactor_validator, readme_grounded_numbers_validator [EXTRACTED 1.00]
- **Layered SQL safety: SafeSQL, EnforceLimit, read-only SQLite** — readme_safe_sql_validator, readme_enforce_limit_validator, readme_read_only_sqlite [EXTRACTED 1.00]
- **CI flow: install dev deps, lint, test offline** — github_workflows_ci_ci_workflow, github_workflows_ci_ruff_step, github_workflows_ci_pytest_step [EXTRACTED 1.00]

## Communities (16 total, 6 thin omitted)

### Community 0 - "Agent Builder & Architecture"
Cohesion: 0.07
Nodes (12): build_agent(), build_model(), Settings, Evidence, build_toolkit(), describe_table(), list_tables(), run_sql() (+4 more)

### Community 1 - "UI Screenshot & CI"
Cohesion: 0.06
Nodes (45): Streamlit app screenshot (full analysis run), Chat panel with user request and agent answer, Plan & trace tab: todo list and tool-call trace (list_tables, run_sql, make_chart), Sidebar: Guardrails AI enabled toggle (Protected), Sidebar: Try a prompt buttons (Full analysis, Quick question, New conversation), CI workflow (GitHub Actions), pytest step (LLM_BACKEND=fake), ruff check step (+37 more)

### Community 2 - "SQL DataStore"
Cohesion: 0.07
Nodes (12): _authorizer(), DataStore, _fmt(), QueryError, QueryResult, sanitize_table_name(), _sql_type(), test_runaway_query_times_out() (+4 more)

### Community 3 - "Number Grounding"
Cohesion: 0.09
Nodes (23): extract_numbers(), is_grounded(), ParsedNumber, ungrounded_numbers(), GuardrailBlocked, check_sql(), find_injection(), _luhn_ok() (+15 more)

### Community 4 - "Guardrail Suite"
Cohesion: 0.09
Nodes (7): GuardrailSuite, OutputReport, EnforceLimit, GroundedNumbers, PIIRedactor, PromptInjection, SafeSQL

### Community 5 - "Sample Data & Event Log"
Cohesion: 0.09
Nodes (6): sample_sales_df(), EventLog, GuardrailEvent, Artifacts, ChartRecord, QueryRecord

### Community 6 - "Session & Settings"
Cohesion: 0.11
Nodes (16): get_settings(), AnalystSession, ChatMessage, dumps(), render_charts(), render_data(), render_guardrails(), render_interrupt() (+8 more)

### Community 7 - "Agent Runner"
Cohesion: 0.16
Nodes (4): message_text(), AgentEvent, AgentRunner, _clip()

### Community 9 - "Agent Tests & Errors"
Cohesion: 0.21
Nodes (5): describe_error(), kinds(), test_full_run_plans_queries_charts_reports_and_answers(), test_prompt_injection_in_the_question_is_blocked_before_the_agent_runs(), test_rate_limit_errors_become_actionable_messages()

### Community 10 - "Streamlit UI Tests"
Cohesion: 0.24
Nodes (7): app(), button(), messages(), test_ask_a_question_end_to_end(), test_attack_prompt_is_blocked_and_logged(), test_chat_is_disabled_until_data_is_loaded(), test_guardrails_toggle_changes_state()

## Knowledge Gaps
- **13 isolated node(s):** `Subagents: data-profiler, sql-analyst, visualizer, critic`, `Virtual file system (/report.md)`, `Human-in-the-loop SQL approval`, `PromptInjection validator`, `EnforceLimit validator` (+8 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 132 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Guardrails AI` connect `UI Screenshot & CI` to `Guardrail Suite`?**
  _High betweenness centrality (0.132) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `GuardrailSuite` (e.g. with `AgentRunner` and `EventLog`) actually correct?**
  _`GuardrailSuite` has 11 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Subagents: data-profiler, sql-analyst, visualizer, critic`, `Virtual file system (/report.md)`, `Human-in-the-loop SQL approval` to the rest of the system?**
  _13 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Agent Builder & Architecture` be split into smaller, more focused modules?**
  _Cohesion score 0.06693877551020408 - nodes in this community are weakly interconnected._
- **Why does `GuardrailSuite` connect `Guardrail Suite` to `Agent Builder & Architecture`, `SQL DataStore`, `Sample Data & Event Log`, `Session & Settings`, `Agent Runner`?**
  _High betweenness centrality (0.095) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `AnalystSession` (e.g. with `AgentEvent` and `AgentRunner`) actually correct?**
  _`AnalystSession` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Should `UI Screenshot & CI` be split into smaller, more focused modules?**
  _Cohesion score 0.057624113475177305 - nodes in this community are weakly interconnected._