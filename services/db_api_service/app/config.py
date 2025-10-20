from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import BaseModel, field_validator


# Application configuration validated via Pydantic.
# Holds paths and runtime flags used across the service.
class Settings(BaseModel):
    CONTRACTS_DIR: Path = Path("app/contracts")
    ALLOWED_TABLES: List[str] = [
        "event_logs_sensors", "devices"
    ]
    STRICT_UNKNOWN_FIELDS: bool = True

    # Normalize ALLOWED_TABLES input before model validation.
    # Accepts a comma-separated string for convenience or any iterable,
    # then returns a deduplicated, lowercase, order-preserving list.
    @field_validator("ALLOWED_TABLES", mode="before")
    @classmethod
    def _normalize_allowed_tables(cls, v):
        # Accept list/tuple/set or comma-separated string (dev convenience)
        if isinstance(v, str):
            v = [x.strip() for x in v.split(",") if x.strip()]
        # Normalize: lowercase + unique order-preserving
        seen = set()
        result = []
        for name in v:
            key = name.strip().lower()
            if key and key not in seen:
                seen.add(key)
                result.append(key)
        return result


# Global settings instance used by the application modules.
settings = Settings()


# Utility: centralized check whether a table name is allowed.
# Comparison is case-insensitive and trims whitespace.
def is_table_allowed(table_name: str) -> bool:
    """Centralized check used by routers/repos."""
    return table_name.strip().lower() in settings.ALLOWED_TABLES
