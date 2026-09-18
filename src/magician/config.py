from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Пути. При non-editable установке __file__ находится в site-packages.
PROJECT_ROOT = Path(os.getenv("MAGICIAN_PROJECT_ROOT", Path.cwd())).resolve()
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "demo.duckdb"
CATALOG_PATH = DATA_DIR / "catalog.yaml"

# Настройки вызовов
MAX_RESULT_ROWS = 200
QUERY_TIMEOUT_SECONDS = 5.0
AGENT_RECURSION_LIMIT = 24

# LLM API
API_KEY = os.getenv("API_KEY")
API_MODEL = os.getenv("API_MODEL", "two/gpu.Qwen/Qwen3.6-27B-FP8")
API_BASE_URL = os.getenv("API_BASE_URL")
