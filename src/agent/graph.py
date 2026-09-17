from langgraph.graph import END, START, StateGraph

from agent.models import AgentState, ClassifiedSource
from agent.nodes import (
    after_analyze,
    analyze,
    fetch_page,
    finalize,
    prepare_next_page,
)
from agent.utils import is_valid_url


builder = StateGraph(AgentState)
builder.add_edge(START, "fetch_page")
builder.add_node("fetch_page", fetch_page)
builder.add_node("analyze", analyze)
builder.add_node("finalize", finalize)
builder.add_node("prepare_next_page", prepare_next_page)
builder.add_edge("fetch_page", "analyze")
builder.add_conditional_edges(
        "analyze",
        after_analyze,
        {"continue": "prepare_next_page", "finalize": "finalize"},
    )
builder.add_edge("prepare_next_page", "fetch_page")
builder.add_edge("finalize", END)


graph = builder.compile()


async def classify_source(url: str) -> ClassifiedSource:
    if not is_valid_url(url):
        raise ValueError(f"Некорректный URL: {url}")

    state = await graph.ainvoke(
        {
            "input_url": url,
            "current_url": url,
            "pages_opened": 0,
            "pages": [],
        }
    )
    return ClassifiedSource.model_validate(state["result"])
