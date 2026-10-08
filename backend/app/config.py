"""Environment-backed application settings."""

from functools import lru_cache

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    oracle_user: str = ""
    oracle_password: SecretStr = SecretStr("")
    oracle_host: str = "oracle.fiap.com.br"
    oracle_port: int = Field(default=1521, ge=1, le=65535)
    oracle_sid: str = "orcl"
    oracle_service_name: str = ""
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.8-flash"
    gemini_fallback_models: str = "gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash,gemini-3.5-flash-lite"
    groq_api_key: SecretStr = SecretStr("")
    groq_model: str = "openai/gpt-oss-20b"
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

    @property
    def oracle_dsn(self) -> str:
        if self.oracle_service_name:
            return f"{self.oracle_host}:{self.oracle_port}/{self.oracle_service_name}"
        return f"{self.oracle_host}:{self.oracle_port}/{self.oracle_sid}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
