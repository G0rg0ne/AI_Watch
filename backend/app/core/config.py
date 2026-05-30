"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the AlphaSignal agent."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"

    # Tavily
    tavily_api_key: str

    # LangSmith
    langchain_tracing_v2: bool = True
    langchain_api_key: str | None = None
    langchain_project: str = "ai-watch-alphasignal"
    langchain_endpoint: str = "https://api.smith.langchain.com"

    # AlphaSignal
    alphasignal_archive_url: str = "https://alphasignal.ai/archive"

    # Database
    database_url: str = "sqlite:////data/ai_watch.db"

    # SMTP
    smtp_host: str
    smtp_port: int = 587
    smtp_user: str
    smtp_password: str
    smtp_use_tls: bool = True
    email_from: str
    email_to: str

    # Scheduler
    run_hour_utc: int = Field(default=8, ge=0, le=23)
    run_minute_utc: int = Field(default=0, ge=0, le=59)
    run_on_startup: bool = False

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
