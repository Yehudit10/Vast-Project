from __future__ import annotations
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    ALLOWED_TABLES: List[str] = Field(default_factory=lambda: ["event_logs_sensors"])
    STRICT_UNKNOWN_FIELDS: bool = True

    # הגדרות מודל (תחליף ל-Config המחלקתי של v1)
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )

    @field_validator("ALLOWED_TABLES", mode="before")
    def _split_allowed_tables(cls, v):
        # מאפשר גם "a,b,c" וגם list
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

settings = Settings()
