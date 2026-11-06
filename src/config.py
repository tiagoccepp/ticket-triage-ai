"""Central configuration. Env-driven, offline-safe defaults.

Set DATABASE_URL=postgresql://... to use Postgres, otherwise SQLite is used.
LLM_PROVIDER=mock (default) keeps everything keyless for CI.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field


class Settings(BaseModel):
    database_url: str = Field(default="sqlite:///./data/triage.db")
    llm_provider: str = Field(default="mock")
    llm_api_key: str = Field(default="")
    llm_base_url: str = Field(default="https://api.openai.com/v1")
    llm_model: str = Field(default="gpt-4o-mini")
    llm_fallback_models: str = Field(default="")
    auto_threshold: float = Field(default=0.80)
    review_threshold: float = Field(default=0.55)
    duplicate_threshold: float = Field(default=0.82)
    environment: str = Field(default="development")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgres")

    @property
    def sqlite_path(self) -> str:
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix):
            return self.database_url[len(prefix):]
        return "./data/triage.db"

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider != "mock" and bool(self.llm_api_key)


def _from_env() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/triage.db"),
        llm_provider=os.getenv("LLM_PROVIDER", "mock"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        llm_fallback_models=os.getenv("LLM_FALLBACK_MODELS", ""),
        auto_threshold=float(os.getenv("AUTO_THRESHOLD", "0.80")),
        review_threshold=float(os.getenv("REVIEW_THRESHOLD", "0.55")),
        duplicate_threshold=float(os.getenv("DUPLICATE_THRESHOLD", "0.82")),
        environment=os.getenv("ENVIRONMENT", "development"),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return _from_env()
