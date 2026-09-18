from __future__ import annotations

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models import BaseChatModel

from magician.agent.models import AgentAnswer
from magician.agent.nodes import create_model, load_storage_tools
from magician.agent.prompts import SYSTEM_PROMPT
from magician.config import AGENT_RECURSION_LIMIT


def build_graph(model: BaseChatModel | None = None):
    """Собирает LangGraph-агента с инструментами локального MCP-сервера."""
    tools = load_storage_tools()
    return create_agent(
        model=model or create_model(),
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        response_format=ToolStrategy(AgentAnswer),
        name="sql_agent",
    )


async def run_agent(question: str, *, model: BaseChatModel | None = None) -> AgentAnswer:
    """Вызов агента для ответа на question."""
    if not question.strip():
        raise ValueError("Вопрос не должен быть пустым.")

    print("→ Анализирую вопрос…", flush=True)
    graph = build_graph(model)
    state = await graph.ainvoke(
        {"messages": [{"role": "user", "content": question.strip()}]},
        {"recursion_limit": AGENT_RECURSION_LIMIT},
    )
    answer = state.get("structured_response")
    if not isinstance(answer, AgentAnswer):
        raise RuntimeError("Агент не вернул структурированный ответ.")

    print("✓ Ответ готов", flush=True)
    return answer
