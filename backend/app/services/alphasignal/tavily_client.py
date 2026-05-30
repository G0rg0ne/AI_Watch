"""Tavily client for fetching AlphaSignal web pages."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from tavily import TavilyClient

from backend.app.core.config import Settings, get_settings
from backend.app.services.alphasignal.archive_parser import (
    build_newsletter_api_url,
    extract_campaign_id,
    sanitize_tavily_json,
)
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
        """Search/extract the AlphaSignal archive listing via its JSON API."""
        archive_api_url = self.settings.alphasignal_archive_api_url
        logger.info("Fetching AlphaSignal archive API: %s", archive_api_url)
        return self.fetch_url(archive_api_url)

    @traceable_step("alphasignal_fetch_archive_api")
    def fetch_archive_listing(self) -> str:
        """Fetch archive listing JSON directly from AlphaSignal."""
        url = self.settings.alphasignal_archive_api_url
        logger.info("Fetching AlphaSignal archive API directly: %s", url)
        response = httpx.get(url, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        return response.text

    @traceable_step("alphasignal_fetch_newsletter_api")
    def fetch_newsletter_content(self, newsletter_url: str) -> str:
        """Fetch newsletter HTML, preferring AlphaSignal JSON API over Tavily."""
        campaign_id = extract_campaign_id(newsletter_url)
        if campaign_id:
            api_url = build_newsletter_api_url(campaign_id, self.settings.alphasignal_base_url)
            logger.info("Fetching AlphaSignal newsletter API directly: %s", api_url)
            response = httpx.get(api_url, timeout=30.0, follow_redirects=True)
            response.raise_for_status()
            return self.unwrap_newsletter_api_response(response.text)

        logger.info("Fetching newsletter via Tavily: %s", newsletter_url)
        tavily_response = self.fetch_url(newsletter_url)
        return self.get_newsletter_content(tavily_response)

    @traceable_step("tavily_fetch_newsletter")
    def fetch_newsletter(self, newsletter_url: str) -> dict[str, Any]:
        """Extract content from a specific newsletter publication."""
        fetch_url = self.resolve_newsletter_fetch_url(newsletter_url)
        return self.fetch_url(fetch_url)

    def resolve_newsletter_fetch_url(self, newsletter_url: str) -> str:
        """Map a public newsletter URL to the AlphaSignal JSON API when possible."""
        campaign_id = extract_campaign_id(newsletter_url)
        if campaign_id:
            api_url = build_newsletter_api_url(campaign_id, self.settings.alphasignal_base_url)
            logger.info("Resolved newsletter API URL: %s", api_url)
            return api_url
        return newsletter_url

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

    def get_newsletter_content(self, tavily_response: dict[str, Any]) -> str:
        """Return newsletter HTML/text, unwrapping AlphaSignal API JSON when needed."""
        content = self.get_extracted_html(tavily_response)
        if not content.strip():
            content = self.get_extracted_content(tavily_response)
        return self.unwrap_newsletter_api_response(content)

    @staticmethod
    def unwrap_newsletter_api_response(content: str) -> str:
        """Extract embedded newsletter HTML from AlphaSignal API JSON payloads."""
        stripped = content.strip()
        if not stripped.startswith("{"):
            return content
        try:
            payload = json.loads(sanitize_tavily_json(stripped))
        except json.JSONDecodeError:
            return content

        data = payload.get("data")
        if isinstance(data, dict):
            html = data.get("html")
            if isinstance(html, str) and html.strip():
                return html
        return content
