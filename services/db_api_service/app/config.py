from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings


# Application configuration validated via Pydantic.
# Holds paths and runtime flags used across the service.
class Settings(BaseSettings):
    CONTRACTS_DIR: Path = Path("app/contracts")
    ALLOWED_TABLES: List[str] = []  # provided via ENV or .env (comma-separated)
    STRICT_UNKNOWN_FIELDS: bool = True

    # Accept comma-separated string or iterable; normalize to lowercase unique list.
    @field_validator("ALLOWED_TABLES", mode="before")
    @classmethod
    def _normalize_allowed_tables(cls, v):
        if isinstance(v, str):
            v = [x.strip() for x in v.split(",") if x.strip()]
        seen = set()
        result: List[str] = []
        for name in v:
            key = name.strip().lower()
            if key and key not in seen:
                seen.add(key)
                result.append(key)
        return result

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance used by the application modules.
settings = Settings()


# Utility: centralized check whether a table name is allowed.
def is_table_allowed(table_name: str) -> bool:
    """Centralized check used by routers/repos."""
    return table_name.strip().lower() in settings.ALLOWED_TABLES
