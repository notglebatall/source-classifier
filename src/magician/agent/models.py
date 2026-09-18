from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


Scalar = str | int | float | bool | None


class QueryResult(BaseModel):
    """Отображаемый результат SQL-инструмента, работающего только на чтение."""

    columns: list[str] = Field(description="Названия столбцов в порядке отображения.")
    rows: list[list[Scalar]] = Field(description="Строки, возвращённые SQL-инструментом.")
    row_count: int = Field(ge=0, description="Количество отображаемых строк.")
    truncated: bool = Field(description="Был ли результат обрезан из-за ограничения строк.")


class AgentAnswer(BaseModel):
    """Итоговый ответ аналитического SQL-агента."""

    status: Literal["answered", "insufficient_data"]
    answer: str = Field(description="Краткий ответ пользователю на языке вопроса.")
    reason: str | None = Field(
        default=None,
        description="Причина, по которой нельзя дать надёжный ответ; иначе null.",
    )
    calculation_plan: str | None = Field(
        default=None,
        description="Применённые фильтры, объединения и вычисления.",
    )
    sql: str | None = Field(
        default=None,
        description="Фактически выполненный итоговый SQL или null, если запрос не обоснован.",
    )
    result: QueryResult | None = Field(
        default=None,
        description="Результат итогового SQL-запроса или null, если запрос не выполнялся.",
    )
    sources: list[str] = Field(
        default_factory=list,
        description="Таблицы и поля каталога, использованные для ответа.",
    )

    @model_validator(mode="after")
    def validate_status(self) -> AgentAnswer:
        if self.status == "answered":
            if not all((self.answer, self.calculation_plan, self.sql, self.result, self.sources)):
                raise ValueError(
                    "Статус answered требует answer, calculation_plan, sql, result и sources"
                )
            if self.reason is not None:
                raise ValueError("Статус answered требует reason=null")
        elif not self.reason:
            raise ValueError("Статус insufficient_data требует указать reason")
        return self
