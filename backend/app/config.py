"""Environment-backed application settings."""

from functools import lru_cache

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = ""
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.5-flash"
    cloudflare_account_id: str = ""
    cloudflare_api_token: SecretStr = SecretStr("")
    vectorize_index: str = "disruptive-architectures-index"
    allowed_origin: AnyHttpUrl = "https://kelsonzh0.github.io"
    max_question_chars: int = Field(default=2000, ge=100, le=10000)
    max_history_turns: int = Field(default=8, ge=0, le=20)
    retrieval_top_k: int = Field(default=8, ge=1, le=30)
    minimum_vector_score: float = Field(default=0.25, ge=0, le=1)
    rate_limit_per_minute: int = Field(default=20, ge=1, le=1000)
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
