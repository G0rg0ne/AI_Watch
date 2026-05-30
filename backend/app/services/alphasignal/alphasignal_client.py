"""HTTP client for fetching AlphaSignal archive and newsletter content."""

from __future__ import annotations

import json
import logging

import httpx

from backend.app.core.config import Settings, get_settings
from backend.app.services.alphasignal.archive_parser import (
    build_newsletter_api_url,
    extract_campaign_id,
    sanitize_json_payload,
)
from backend.app.services.tracing import traceable_step

logger = logging.getLogger(__name__)


class AlphaSignalClient:
    """Fetch archive and newsletter content from AlphaSignal JSON APIs."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @traceable_step("alphasignal_fetch_archive_api")
    def fetch_archive_listing(self) -> str:
        """Fetch archive listing JSON from the AlphaSignal API."""
        url = self.settings.alphasignal_archive_api_url
        logger.info("Fetching AlphaSignal archive API: %s", url)
        response = httpx.get(url, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        return response.text

    @traceable_step("alphasignal_fetch_newsletter_api")
    def fetch_newsletter_content(self, newsletter_url: str) -> str:
        """Fetch newsletter HTML from the AlphaSignal JSON API."""
        campaign_id = extract_campaign_id(newsletter_url)
        if not campaign_id:
            raise ValueError(
                f"Cannot resolve AlphaSignal campaign id from URL: {newsletter_url!r}"
            )
        api_url = build_newsletter_api_url(campaign_id, self.settings.alphasignal_base_url)
        logger.info("Fetching AlphaSignal newsletter API: %s", api_url)
        response = httpx.get(api_url, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        return self.unwrap_newsletter_api_response(response.text)

    @staticmethod
    def unwrap_newsletter_api_response(content: str) -> str:
        """Extract embedded newsletter HTML from AlphaSignal API JSON payloads."""
        stripped = content.strip()
        if not stripped.startswith("{"):
            return content
        try:
            payload = json.loads(sanitize_json_payload(stripped))
        except json.JSONDecodeError:
            return content

        data = payload.get("data")
        if isinstance(data, dict):
            html = data.get("html")
            if isinstance(html, str) and html.strip():
                return html
        return content
