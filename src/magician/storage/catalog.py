from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from magician.config import CATALOG_PATH


@lru_cache(maxsize=4)
def load_catalog(path: str | Path | None = None) -> dict[str, Any]:
    resolved_path = Path(path) if path else CATALOG_PATH
    with resolved_path.open(encoding="utf-8") as catalog_file:
        catalog = yaml.safe_load(catalog_file)

    if not isinstance(catalog, dict) or not isinstance(catalog.get("tables"), list):
        raise ValueError(f"Некорректный каталог: {resolved_path}")
    return catalog


def table_columns(catalog: dict[str, Any]) -> dict[str, set[str]]:
    return {
        table["name"]: {column["name"] for column in table["columns"]}
        for table in catalog["tables"]
    }


def inspectable_columns(catalog: dict[str, Any]) -> dict[str, set[str]]:
    return {
        table["name"]: set(table.get("inspectable_columns", []))
        for table in catalog["tables"]
    }
