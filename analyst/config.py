from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

MODEL_CHOICES = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
]


class Settings(BaseSettings):
    """Configuration from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_backend: Literal["groq", "fake"] = "groq"
    groq_api_key: str | None = None
    groq_model: str = MODEL_CHOICES[0]

    max_rows: int = 200  # hard cap on rows returned by one query
    preview_rows: int = 25  # rows shown to the model per query
    query_timeout_s: float = 8.0
    max_upload_mb: int = 25
    recursion_limit: int = 80  # LangGraph steps per run


@lru_cache
def get_settings() -> Settings:
    return Settings()
