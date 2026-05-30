"""Tavily client for fetching AlphaSignal web pages."""

from __future__ import annotations

import logging
from typing import Any

from tavily import TavilyClient

from backend.app.core.config import Settings, get_settings
from backend.app.services.tracing import traceable_step

logger = logging.getLogger(__name__)


class AlphaSignalTavilyClient:
    """Fetch archive and newsletter content using Tavily."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = TavilyClient(api_key=self.settings.tavily_api_key)

    @traceable_step("tavily_fetch_url")
    def fetch_url(self, url: str) -> dict[str, Any]:
        """Extract raw content from a URL via Tavily."""
        logger.info("Fetching URL via Tavily: %s", url)
        result = self._client.extract(urls=[url])
        return result

    @traceable_step("tavily_search_archive")
    def search_archive(self) -> dict[str, Any]:
        """Search/extract the AlphaSignal archive page."""
        archive_url = self.settings.alphasignal_archive_url
        logger.info("Fetching AlphaSignal archive: %s", archive_url)
        return self.fetch_url(archive_url)

    @traceable_step("tavily_fetch_newsletter")
    def fetch_newsletter(self, newsletter_url: str) -> dict[str, Any]:
        """Extract content from a specific newsletter page."""
        return self.fetch_url(newsletter_url)

    def get_extracted_content(self, tavily_response: dict[str, Any]) -> str:
        """Normalize Tavily extract response into a single text blob."""
        results = tavily_response.get("results") or []
        if not results:
            raw_content = tavily_response.get("content") or tavily_response.get("raw_content")
            if isinstance(raw_content, str):
                return raw_content
            return ""

        parts: list[str] = []
        for item in results:
            if isinstance(item, dict):
                for key in ("raw_content", "content", "text"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        parts.append(value.strip())
                        break
        return "\n\n".join(parts)

    def get_extracted_html(self, tavily_response: dict[str, Any]) -> str:
        """Return HTML content when available, otherwise fall back to text."""
        results = tavily_response.get("results") or []
        for item in results:
            if isinstance(item, dict):
                for key in ("raw_content", "content", "html"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        return value
        return self.get_extracted_content(tavily_response)
