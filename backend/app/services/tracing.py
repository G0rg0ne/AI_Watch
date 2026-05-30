"""LangSmith tracing configuration and helpers."""

from __future__ import annotations

import os
from functools import wraps
from typing import Any, Callable, TypeVar

from backend.app.core.config import Settings, get_settings

F = TypeVar("F", bound=Callable[..., Any])


def configure_langsmith(settings: Settings | None = None) -> None:
    """Apply LangSmith environment variables before agent runs."""
    cfg = settings or get_settings()
    os.environ["LANGCHAIN_TRACING_V2"] = str(cfg.langchain_tracing_v2).lower()
    os.environ["LANGCHAIN_PROJECT"] = cfg.langchain_project
    os.environ["LANGCHAIN_ENDPOINT"] = cfg.langchain_endpoint
    if cfg.langchain_api_key:
        os.environ["LANGCHAIN_API_KEY"] = cfg.langchain_api_key


def traceable_step(name: str) -> Callable[[F], F]:
    """Decorator that wraps a function with LangSmith tracing when available."""

    def decorator(func: F) -> F:
        try:
            from langsmith import traceable

            return traceable(name=name)(func)  # type: ignore[return-value]
        except ImportError:
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                return func(*args, **kwargs)

            return wrapper  # type: ignore[return-value]

    return decorator
