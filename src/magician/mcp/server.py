from __future__ import annotations

import logging
from typing import Any

from mcp.server import MCPServer

from magician.storage.catalog import load_catalog
from magician.storage.query import inspect_distinct_values, run_read_only_query


logger = logging.getLogger(__name__)


mcp = MCPServer(
    "sql-agent-storage",
    instructions=(
        "Перед составлением SQL прочитай каталог. Учитывай гранулярность таблиц, "
        "семантику дат, определения показателей и разрешённые объединения. Используй "
        "inspect_values, только если точное категориальное значение неизвестно."
    ),
)


@mcp.tool()
def get_catalog() -> dict[str, Any]:
    """Вернуть бизнес-определения, гранулярность таблиц, поля, метрики и связи."""
    return load_catalog()


@mcp.tool()
def inspect_values(
    table: str,
    column: str,
    search: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Вернуть значения разрешённого категориального поля с необязательным фильтром."""
    return inspect_distinct_values(table, column, search=search, limit=limit)


@mcp.tool()
def run_sql(sql: str) -> dict[str, Any]:
    """Выполнить один SELECT к таблицам DuckDB с ограничениями времени и числа строк."""
    try:
        return run_read_only_query(sql)
    except Exception:
        logger.exception("Ошибка выполнения run_sql; sql=%s", sql)
        raise


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
