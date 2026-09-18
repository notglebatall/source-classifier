from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any

import duckdb
from sqlglot import exp, parse

from magician.config import DATABASE_PATH, MAX_RESULT_ROWS, QUERY_TIMEOUT_SECONDS
from magician.storage.catalog import inspectable_columns, load_catalog, table_columns


class QueryRejected(ValueError):
    pass


def _quote_identifier(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def validate_query(sql: str, *, catalog: dict[str, Any] | None = None) -> str:
    if not sql.strip():
        raise QueryRejected("SQL-запрос пуст.")

    try:
        statements = [statement for statement in parse(sql, read="duckdb") if statement]
    except Exception as exc:
        raise QueryRejected(f"Не удалось разобрать SQL: {exc}") from exc

    if len(statements) != 1 or not isinstance(statements[0], exp.Query):
        raise QueryRejected("Разрешён ровно один запрос SELECT или WITH ... SELECT.")

    statement = statements[0]
    cte_names = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
    allowed_tables = set(table_columns(catalog or load_catalog()))
    referenced_tables = set()
    for table in statement.find_all(exp.Table):
        if table.catalog or table.db:
            raise QueryRejected("Квалифицированные имена и системные схемы запрещены.")
        table_name = table.name.lower()
        if table_name not in cte_names:
            referenced_tables.add(table_name)

    forbidden = sorted(referenced_tables - allowed_tables)
    if forbidden:
        raise QueryRejected(f"Таблицы не входят в каталог: {', '.join(forbidden)}")
    if not referenced_tables:
        raise QueryRejected("Запрос должен читать хотя бы одну таблицу из каталога.")

    return statement.sql(dialect="duckdb")


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def _open_read_only(path: Path) -> duckdb.DuckDBPyConnection:
    if not path.exists():
        raise FileNotFoundError(f"Тестовая база не найдена: {path}. Выполните sql-agent-init-db.")
    return duckdb.connect(
        str(path),
        read_only=True,
        config={"enable_external_access": "false", "allow_unsigned_extensions": "false"},
    )


def run_read_only_query(
    sql: str,
    *,
    path: str | Path | None = None,
    max_rows: int = MAX_RESULT_ROWS,
    timeout_seconds: float = QUERY_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    normalized_sql = validate_query(sql)
    wrapped_sql = f"SELECT * FROM ({normalized_sql}) AS query_result LIMIT {max_rows + 1}"
    resolved_path = Path(path) if path else DATABASE_PATH
    connection = _open_read_only(resolved_path)
    started = perf_counter()

    def execute() -> tuple[list[str], list[tuple[Any, ...]]]:
        cursor = connection.execute(wrapped_sql)
        return [column[0] for column in cursor.description], cursor.fetchall()

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(execute)
    try:
        try:
            columns, rows = future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            connection.interrupt()
            try:
                future.result()
            except Exception:
                pass
            raise TimeoutError(f"Запрос превысил лимит {timeout_seconds:g} с.") from exc
    finally:
        executor.shutdown(wait=True)
        connection.close()

    truncated = len(rows) > max_rows
    visible_rows = rows[:max_rows]
    return {
        "columns": columns,
        "rows": [[_json_value(value) for value in row] for row in visible_rows],
        "row_count": len(visible_rows),
        "truncated": truncated,
        "elapsed_ms": round((perf_counter() - started) * 1000, 2),
    }


def inspect_distinct_values(
    table: str,
    column: str,
    *,
    search: str | None = None,
    limit: int = 20,
    path: str | Path | None = None,
) -> dict[str, Any]:
    catalog = load_catalog()
    allowed = inspectable_columns(catalog)
    if table not in allowed:
        raise QueryRejected(f"Таблица не входит в каталог: {table}")
    if column not in allowed[table]:
        raise QueryRejected(f"Поле нельзя просматривать через inspect_values: {table}.{column}")
    if not 1 <= limit <= 50:
        raise QueryRejected("limit должен быть от 1 до 50.")

    table_sql = _quote_identifier(table)
    column_sql = _quote_identifier(column)
    where_sql = ""
    parameters: list[Any] = []
    if search:
        where_sql = f"WHERE CAST({column_sql} AS VARCHAR) ILIKE ?"
        parameters.append(f"%{search}%")

    sql = (
        f"SELECT {column_sql}, COUNT(*) AS occurrences "
        f"FROM {table_sql} {where_sql} "
        f"GROUP BY {column_sql} ORDER BY occurrences DESC, {column_sql} LIMIT ?"
    )
    parameters.append(limit)
    resolved_path = Path(path) if path else DATABASE_PATH
    connection = _open_read_only(resolved_path)
    try:
        rows = connection.execute(sql, parameters).fetchall()
    finally:
        connection.close()

    return {
        "table": table,
        "column": column,
        "values": [
            {"value": _json_value(value), "occurrences": occurrences}
            for value, occurrences in rows
        ],
    }
