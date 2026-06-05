"""Application settings loaded from environment variables."""

from datetime import date
from functools import lru_cache

from pydantic import Field, field_validator
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

    # LangSmith
    langchain_tracing_v2: bool = True
    langchain_api_key: str | None = None
    langchain_project: str = "ai-watch-alphasignal"
    langchain_endpoint: str = "https://api.smith.langchain.com"
    langsmith_summarizer_prompt: str = "alphasignal-newsletter-summarizer:prod"

    # AlphaSignal
    alphasignal_base_url: str = "https://alphasignal.ai"
    alphasignal_news_api_url: str = "https://api.alphasignal.ai/api/news"
    alphasignal_news_detail_api_url: str = "https://api.alphasignal.ai/api/news/detail"
    alphasignal_archive_limit: int = Field(default=10, ge=1, le=100)
    alphasignal_start_date: date | None = None

    @field_validator("alphasignal_start_date", mode="before")
    @classmethod
    def empty_start_date_to_none(cls, value: object) -> object:
        """Treat unset or blank ALPHASIGNAL_START_DATE as no cutoff."""
        if value is None or value == "":
            return None
        return value

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
