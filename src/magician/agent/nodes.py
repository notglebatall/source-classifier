from __future__ import annotations

import sys
from typing import Any
from pydantic import BaseModel, Field

from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent


from magician.config import (
    API_BASE_URL,
    API_KEY,
    API_MODEL,
    PROJECT_ROOT,
)


def create_model() -> ChatOpenAI:
    options: dict[str, Any] = {
        "model": API_MODEL,
    }
    if API_KEY:
        options["api_key"] = API_KEY
    if API_BASE_URL:
        options["base_url"] = API_BASE_URL
    return ChatOpenAI(**options)


class InspectValuesInput(BaseModel):
    table: str = Field(description="Название таблицы из каталога.")
    column: str = Field(description="Название категориального поля, доступного для просмотра.")
    search: str | None = Field(default=None, description="Необязательный фильтр по подстроке.")
    limit: int = Field(default=20, ge=1, le=50)


class RunSqlInput(BaseModel):
    sql: str = Field(description="Один запрос SELECT или WITH ... SELECT только для чтения.")


def _server_parameters() -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-u", "-m", "magician.mcp.server"],
        cwd=PROJECT_ROOT,
    )


def _print_tool_status(name: str, arguments: dict[str, Any]) -> None:
    if name == "get_catalog":
        message = "Изучаю доступные таблицы и показатели"
    elif name == "inspect_values":
        message = f"Проверяю значения {arguments['table']}.{arguments['column']}"
    elif name == "run_sql":
        message = "Выполняю запрос к данным"
    else:
        message = f"Вызываю инструмент {name}"

    print(f"→ {message}…", flush=True)


async def _call_tool(name: str, arguments: dict[str, Any]) -> Any:
    _print_tool_status(name, arguments)
    
    async with stdio_client(_server_parameters()) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments=arguments)

    if getattr(result, "is_error", False):
        message = " ".join(
            block.text for block in result.content if isinstance(block, TextContent)
        )
        raise RuntimeError(message or f"Ошибка MCP-инструмента {name}")
    
    if result.structured_content is not None:
        return result.structured_content
    
    return "\n".join(
        block.text for block in result.content if isinstance(block, TextContent)
    )


async def _get_catalog() -> Any:
    return await _call_tool("get_catalog", {})


async def _inspect_values(
    table: str,
    column: str,
    search: str | None = None,
    limit: int = 20,
) -> Any:
    return await _call_tool(
        "inspect_values",
        {"table": table, "column": column, "search": search, "limit": limit},
    )


async def _run_sql(sql: str) -> Any:
    return await _call_tool("run_sql", {"sql": sql})


def load_storage_tools() -> list[StructuredTool]:
    return [
        StructuredTool.from_function(
            coroutine=_get_catalog,
            name="get_catalog",
            description="Получить полный бизнес-каталог витрин, полей, связей и метрик.",
        ),
        StructuredTool.from_function(
            coroutine=_inspect_values,
            name="inspect_values",
            description="Проверить значения разрешённого категориального поля.",
            args_schema=InspectValuesInput,
        ),
        StructuredTool.from_function(
            coroutine=_run_sql,
            name="run_sql",
            description="Выполнить один безопасный запрос к витринам каталога только для чтения.",
            args_schema=RunSqlInput,
        ),
    ]
