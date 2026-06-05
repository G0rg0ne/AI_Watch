"""HTTP client for fetching AlphaSignal archive and newsletter content."""

from __future__ import annotations

import json
import logging
from datetime import date
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx

from backend.app.core.config import Settings, get_settings
from backend.app.services.alphasignal.archive_parser import (
    build_newsletter_api_url,
    extract_campaign_id,
    parse_api_timestamp,
    sanitize_json_payload,
)
from backend.app.services.alphasignal.browserbase_fetcher import BrowserbaseFetcher
from backend.app.services.tracing import traceable_step

logger = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://alphasignal.ai/archive",
}


class AlphaSignalClient:
    """Fetch archive and newsletter content from AlphaSignal JSON APIs."""

    def __init__(
        self,
        settings: Settings | None = None,
        browserbase_fetcher: BrowserbaseFetcher | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._browserbase_fetcher = browserbase_fetcher

    @property
    def browserbase_fetcher(self) -> BrowserbaseFetcher:
        if self._browserbase_fetcher is None:
            self._browserbase_fetcher = BrowserbaseFetcher(settings=self.settings)
        return self._browserbase_fetcher

    def _build_archive_api_url(self, page: int) -> str:
        """Build a paginated archive API URL from the configured archive API URL."""
        parsed = urlparse(self.settings.alphasignal_archive_api_url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        query["page"] = [str(page)]
        if "limit" not in query:
            query["limit"] = [str(self.settings.alphasignal_archive_limit)]
        new_query = urlencode(query, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    def _fetch_url_direct(self, url: str) -> str:
        """Fetch a URL directly from the current host via httpx."""
        response = httpx.get(
            url,
            timeout=30.0,
            follow_redirects=True,
            headers=_DEFAULT_HEADERS,
        )
        response.raise_for_status()
        return response.text.strip()

    def _fetch_url_browserbase(self, url: str) -> str:
        """Fetch a URL via Browserbase-hosted Chromium."""
        return self.browserbase_fetcher.fetch_url(url)

    def _fetch_url(self, url: str) -> str:
        """Fetch a URL using the configured retrieval mode."""
        mode = self.settings.alphasignal_fetch_mode
        if mode == "browserbase":
            logger.info("Fetching AlphaSignal via Browserbase: %s", url)
            return self._fetch_url_browserbase(url)

        if mode == "auto":
            try:
                logger.info("Fetching AlphaSignal directly (auto mode): %s", url)
                return self._fetch_url_direct(url)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 403:
                    raise
                logger.warning(
                    "Direct AlphaSignal fetch returned 403 for %s; falling back to Browserbase",
                    url,
                )
                return self._fetch_url_browserbase(url)

        logger.info("Fetching AlphaSignal directly: %s", url)
        return self._fetch_url_direct(url)

    @staticmethod
    def _page_oldest_date(items: list[dict]) -> date | None:
        """Return the publication date of the oldest row on an archive page."""
        oldest: date | None = None
        for item in items:
            timestamp = item.get("timestamp")
            if not timestamp:
                continue
            try:
                published_at = parse_api_timestamp(str(timestamp))
            except ValueError:
                continue
            item_date = published_at.date()
            if oldest is None or item_date < oldest:
                oldest = item_date
        return oldest

    @traceable_step("alphasignal_fetch_archive_api")
    def fetch_archive_listing(self, start_date: date | None = None) -> str:
        """Fetch archive listing JSON, paginating when needed for backfill."""
        first_url = self._build_archive_api_url(1)
        logger.info("Fetching AlphaSignal archive API: %s", first_url)
        content = self._fetch_url(first_url)

        if not content.startswith("{"):
            return content

        first_payload = json.loads(sanitize_json_payload(content))
        metadata = first_payload.get("metadata") or {}
        total_pages = int(metadata.get("total_pages") or 1)
        all_items: list[dict] = list(first_payload.get("data") or [])

        should_paginate = start_date is not None and total_pages > 1
        if not should_paginate:
            return content

        page = 2
        while page <= total_pages:
            page_url = self._build_archive_api_url(page)
            logger.info("Fetching AlphaSignal archive API page %s: %s", page, page_url)
            page_content = self._fetch_url(page_url)
            page_payload = json.loads(sanitize_json_payload(page_content))
            page_items = page_payload.get("data") or []
            if not page_items:
                break

            all_items.extend(page_items)

            if start_date is not None:
                oldest_on_page = self._page_oldest_date(page_items)
                if oldest_on_page is not None and oldest_on_page < start_date:
                    logger.info(
                        "Stopping archive pagination at page %s; oldest entry %s is before start date %s",
                        page,
                        oldest_on_page,
                        start_date,
                    )
                    break

            page += 1

        merged_payload = {
            "metadata": {
                **metadata,
                "current_page": 1,
                "total_pages": 1,
                "limit": len(all_items),
                "total_records": len(all_items),
            },
            "data": all_items,
        }
        logger.info("Fetched %d archive entries across paginated API calls", len(all_items))
        return json.dumps(merged_payload)

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
        content = self._fetch_url(api_url)
        return self.unwrap_newsletter_api_response(content)

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
