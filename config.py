"""Application configuration and environment loading for CatalystIQ."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

MP_API_KEY: str = os.getenv("MP_API_KEY", "")
BRENDA_EMAIL: str = os.getenv("BRENDA_EMAIL", "")
BRENDA_PASSWORD: str = os.getenv("BRENDA_PASSWORD", "")
S2_API_KEY: str = os.getenv("S2_API_KEY", "")
OCP_DATA_DIR: str = os.getenv("OCP_DATA_DIR", str(Path("./data").resolve()))
CACHE_DB_PATH: str = os.getenv("CACHE_DB_PATH", str(Path("./query_cache.sqlite").resolve()))
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///catalystiq.db")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
