from __future__ import annotations

import json
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage

from agent.models import (
    GEOGRAPHY,
    SOURCE_TYPES,
    SYSTEM_PROMPT,
    TOPICS,
    AgentState,
    ClassifiedSource,
    ResearchDecision,
    taxonomy_prompt,
)
from agent.utils import create_model, download_page, extract_json, get_host

MAX_PAGES = 5


async def fetch_page(state: AgentState) -> dict[str, Any]:
    page = await download_page(state["current_url"], state.get("source_host"))
    pages = [*state.get("pages", []), page]
    update: dict[str, Any] = {
        "pages": pages,
        "pages_opened": state.get("pages_opened", 0) + 1,
    }
    if page["available"] and not state.get("source_host"):
        update["source_host"] = get_host(page["url"])
    return update


async def analyze(state: AgentState) -> dict[str, Any]:
    pages = state["pages"]
    successful = [page for page in pages if page["available"]]
    if not successful:
        return {
            "decision": ResearchDecision(
                explanation="Входная страница недоступна.",
                enough_data=False,
            ).model_dump(),
            "next_url": None,
        }

    visited = {page["requested_url"] for page in pages} | {page["url"] for page in pages}
    candidate_links = [
        link for link in successful[-1]["links"] if link["url"] not in visited
    ]
    available_links = [
        {"number": number, **link}
        for number, link in enumerate(candidate_links, start=1)
    ]
    evidence = [
        {key: value for key, value in page.items() if key != "links"}
        for page in successful
    ]
    previous_decision = state.get("decision")
    if previous_decision:
        previous_decision = {
            key: value
            for key, value in previous_decision.items()
            if key != "next_link_number"
        }
    payload = {
        "input_url": state["input_url"],
        "opened_pages": evidence,
        "available_links": available_links,
        "previous_decision": previous_decision,
        "pages_left": MAX_PAGES - state["pages_opened"],
    }

    try:
        response = await create_model().ainvoke(
            [
                SystemMessage(SYSTEM_PROMPT.format(taxonomy=taxonomy_prompt())),
                HumanMessage(json.dumps(payload, ensure_ascii=False)),
            ]
        )
        decision = ResearchDecision.model_validate_json(extract_json(str(response.content)))
    except Exception as exc:
        decision = ResearchDecision(
            explanation=f"Не удалось проанализировать страницы: {exc}",
            enough_data=False,
        )

    next_url = None
    if decision.next_link_number is not None:
        link_index = decision.next_link_number - 1
        if 0 <= link_index < len(available_links):
            next_url = available_links[link_index]["url"]
        else:
            decision.next_link_number = None
    return {"decision": decision.model_dump(), "next_url": next_url}


def after_analyze(state: AgentState) -> Literal["continue", "finalize"]:
    decision = ResearchDecision.model_validate(state["decision"])
    if (
        decision.enough_data
        or state["pages_opened"] >= MAX_PAGES
        or not state.get("next_url")
    ):
        return "finalize"
    return "continue"


def prepare_next_page(state: AgentState) -> dict[str, str]:
    next_url = state.get("next_url")
    if not next_url:
        raise ValueError("Следующая страница не выбрана")
    return {"current_url": next_url}


def finalize(state: AgentState) -> dict[str, Any]:
    decision_data = state.get("decision")
    decision = (
        ResearchDecision.model_validate(decision_data)
        if decision_data
        else ResearchDecision(explanation="Входная страница недоступна.")
    )
    successful_pages = [page for page in state.get("pages", []) if page["available"]]
    evidence_urls = list(dict.fromkeys(page["url"] for page in successful_pages))
    canonical_url = None
    if successful_pages:
        first_page = successful_pages[0]
        canonical_url = first_page.get("canonical_url") or first_page["url"]
    geography = [value for value in decision.geography if value in GEOGRAPHY]
    topics = [value for value in decision.topics if value in TOPICS]

    classified = all(
        (
            decision.enough_data,
            decision.source_name,
            decision.source_type in SOURCE_TYPES,
            bool(GEOGRAPHY and TOPICS and SOURCE_TYPES),
            bool(evidence_urls),
            len(geography) == len(decision.geography),
            len(topics) == len(decision.topics),
        )
    )
    result = ClassifiedSource(
        input_url=state["input_url"],
        canonical_url=canonical_url,
        source_name=decision.source_name,
        geography=geography,
        topics=topics,
        source_type=decision.source_type if decision.source_type in SOURCE_TYPES else "",
        evidence_urls=evidence_urls,
        explanation=decision.explanation,
        classified=classified,
    )
    return {"result": result.model_dump()}
