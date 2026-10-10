from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

from analyst.agent import prompts
from analyst.agent.fake_model import ScriptedAnalystModel
from analyst.config import Settings
from analyst.tools.toolkit import Toolkit


def build_model(settings: Settings, model_name: str | None = None) -> BaseChatModel:
    if settings.llm_backend == "fake":
        return ScriptedAnalystModel()
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not set (or use LLM_BACKEND=fake for the offline demo).")
    from langchain_groq import ChatGroq

    return ChatGroq(
        model=model_name or settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=0,
        max_retries=5,  # rides out per-minute limits (the client honours retry-after); see runner
        timeout=90,
    )


def build_agent(
    *,
    model: BaseChatModel,
    toolkit: Toolkit,
    require_approval: bool = False,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """A LangChain deep agent: planning (write_todos), a virtual file system, and four
    specialised subagents that work in isolated context windows."""
    from deepagents import create_deep_agent
    from langchain.agents.middleware import TodoListMiddleware

    approval = {"run_sql": True} if require_approval else None
    subagents = [
        {
            "name": "data-profiler",
            "description": "Audits data quality: nulls, duplicates, outliers, odd values. Use before analysis.",
            "system_prompt": prompts.DATA_PROFILER,
            "tools": [toolkit.list_tables, toolkit.describe_table, toolkit.run_sql],
        },
        {
            "name": "sql-analyst",
            "description": "Answers one focused analytical question with SQL and returns exact numbers with query_ids.",
            "system_prompt": prompts.SQL_ANALYST,
            "tools": [toolkit.list_tables, toolkit.describe_table, toolkit.run_sql],
        },
        {
            "name": "visualizer",
            "description": "Creates charts from existing query_ids. Give it the query_ids and what each should show.",
            "system_prompt": prompts.VISUALIZER,
            "tools": [toolkit.make_chart],
        },
        {
            "name": "critic",
            "description": "Fact-checks draft findings against the data; replies APPROVED or a list of corrections.",
            "system_prompt": prompts.CRITIC,
            "tools": [toolkit.run_sql],
        },
    ]
    if approval:  # human review applies inside subagents too
        for sub in subagents:
            if toolkit.run_sql in sub["tools"]:
                sub["interrupt_on"] = approval

    return create_deep_agent(
        model=model,
        tools=toolkit.all,
        system_prompt=prompts.MAIN,
        subagents=subagents,
        middleware=[TodoListMiddleware()],  # the `write_todos` planning tool
        interrupt_on=approval,
        checkpointer=checkpointer or MemorySaver(),
        name="data-analyst",
    )
