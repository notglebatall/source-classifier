from typing import Any, TypedDict

from pydantic import BaseModel, Field


GEOGRAPHY: tuple[str, ...] = (
    # "Россия",
)

TOPICS: tuple[str, ...] = (
    # "Технологии",
)

SOURCE_TYPES: tuple[str, ...] = (
    # "СМИ",
)


SYSTEM_PROMPT = """\
Ты классифицируешь источник целиком, а не отдельную публикацию.
Используй только факты из открытых страниц. Не угадывай метки.
Метки можно выбирать только из закрытой таксономии ниже.

{taxonomy}

Верни только JSON со следующими полями:
source_name, geography, topics, source_type, explanation,
enough_data, next_link_number.

next_link_number — номер ссылки из available_links, которую нужно открыть следующей.
Выбирай его только если данных не хватает, иначе верни null.
Если таксономия пуста, данных недостаточно или источник нельзя уверенно определить,
установи enough_data=false. Не используй внешние сайты и веб-поиск.
"""


def taxonomy_prompt() -> str:
    return (
        f"География: {list(GEOGRAPHY)}\n"
        f"Тематики: {list(TOPICS)}\n"
        f"Типы источника: {list(SOURCE_TYPES)}"
    )


class AgentState(TypedDict, total=False):
    input_url: str
    current_url: str
    source_host: str
    pages_opened: int
    pages: list[dict[str, Any]]
    decision: dict[str, Any]
    next_url: str | None
    result: dict[str, Any]


class ClassifiedSource(BaseModel):
    input_url: str
    canonical_url: str | None = None
    source_name: str | None = None
    geography: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    source_type: str = ""
    evidence_urls: list[str] = Field(default_factory=list)
    explanation: str
    classified: bool


class ResearchDecision(BaseModel):
    source_name: str | None = None
    geography: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    source_type: str = ""
    explanation: str
    enough_data: bool = False
    next_link_number: int | None = Field(default=None, ge=1)
