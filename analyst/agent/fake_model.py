"""A scripted chat model so the whole app (and its tests) can run offline.

It plays a fixed analyst workflow: plan -> list tables -> run SQL -> chart -> report -> answer.
It does *not* pretend to be smart; it exists to exercise the real agent graph, tools,
guardrails and UI without network access or an API key.
"""

import json
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ScriptedAnalystModel(BaseChatModel):
    """Walks through a fixed tool-calling script, then answers from the SQL result."""

    @property
    def _llm_type(self) -> str:
        return "scripted-analyst"

    def bind_tools(self, tools, **kwargs: Any):  # tool schemas are irrelevant to a script
        return self

    @staticmethod
    def _call(name: str, args: dict, idx: int) -> AIMessage:
        return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{idx}"}])

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any):
        last_human = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
        turn = messages[last_human:]
        tool_msgs = [m for m in turn if isinstance(m, ToolMessage)]
        step = len(tool_msgs)
        question = str(messages[last_human].content)

        script = [
            (
                "write_todos",
                {
                    "todos": [
                        {"content": "Inspect tables", "status": "in_progress"},
                        {"content": "Query revenue by region", "status": "pending"},
                        {"content": "Chart and report", "status": "pending"},
                    ]
                },
            ),
            ("list_tables", {}),
            (
                "run_sql",
                {
                    "query": "SELECT region, ROUND(SUM(revenue), 2) AS total_revenue "
                    "FROM sample_sales GROUP BY region ORDER BY total_revenue DESC",
                    "title": "Revenue by region",
                },
            ),
            (
                "make_chart",
                {
                    "query_id": "q1",
                    "chart_type": "bar",
                    "x": "region",
                    "y": "total_revenue",
                    "title": "Revenue by region",
                },
            ),
        ]
        if step < len(script):
            name, args = script[step]
            return self._result(self._call(name, args, step))

        sql_result = next((str(m.content) for m in tool_msgs if "query_id: q1" in str(m.content)), "")
        rows = [ln for ln in sql_result.splitlines() if ln.startswith("|") and "---" not in ln][1:]
        top = [c.strip() for c in rows[0].strip("|").split("|")] if rows else ["n/a", "n/a"]
        figure = top[1]

        if step == len(script):
            report = f"# Revenue report\n\n## Summary\nTop region by revenue: **{top[0]}** with {figure}.\n"
            return self._result(
                self._call("write_file", {"file_path": "/report.md", "content": report}, step)
            )
        return self._result(
            AIMessage(content=f"{top[0]} has the highest revenue ({figure}). Question: {question[:60]}")
        )

    @staticmethod
    def _result(message: AIMessage) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=message)])


def tool_args_json(message: AIMessage) -> str:
    return json.dumps([c["args"] for c in message.tool_calls])
