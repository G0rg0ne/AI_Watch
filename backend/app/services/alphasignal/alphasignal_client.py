"""HTTP client for fetching AlphaSignal archive and newsletter content."""

from __future__ import annotations

import json
import logging
from datetime import date

import httpx

from backend.app.core.config import Settings, get_settings
from backend.app.services.alphasignal.archive_parser import (
    extract_api_items,
    extract_article_html_from_page,
    is_news_article_url,
    parse_api_timestamp,
    sanitize_json_payload,
)
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
    "Origin": "https://alphasignal.ai",
    "Referer": "https://alphasignal.ai/",
}


class AlphaSignalClient:
    """Fetch archive listings and article content from AlphaSignal."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _build_news_api_body(self, page: int) -> dict[str, object]:
        """Build the JSON body for the official AlphaSignal news listing API."""
        return {
            "page": page,
            "limit": self.settings.alphasignal_archive_limit,
            "sort": "latest",
            "timeframe": "latest",
        }

    @staticmethod
    def _normalize_news_api_payload(raw_payload: dict) -> dict:
        """Normalize official news API responses to a flat listing JSON shape."""
        outer = raw_payload.get("data")
        if not isinstance(outer, dict):
            return raw_payload
        metadata = outer.get("metadata") or {}
        items = outer.get("data") or []
        return {
            "metadata": metadata,
            "data": items,
        }

    def _fetch_url(self, url: str) -> str:
        """Fetch a URL directly via httpx GET."""
        logger.info("Fetching AlphaSignal: %s", url)
        response = httpx.get(
            url,
            timeout=30.0,
            follow_redirects=True,
            headers=_DEFAULT_HEADERS,
        )
        response.raise_for_status()
        return response.text.strip()

    def _fetch_post(self, url: str, body: dict[str, object]) -> str:
        """POST JSON to a URL directly via httpx."""
        logger.info("Posting to AlphaSignal: %s", url)
        response = httpx.post(
            url,
            json=body,
            timeout=30.0,
            follow_redirects=True,
            headers=_DEFAULT_HEADERS,
        )
        response.raise_for_status()
        return response.text.strip()

    @staticmethod
    def _page_oldest_date(items: list[dict]) -> date | None:
        """Return the publication date of the oldest row on an archive page."""
        oldest: date | None = None
        for item in items:
            publish_time = item.get("publish_time")
            if not publish_time:
                continue
            try:
                published_at = parse_api_timestamp(str(publish_time))
            except ValueError:
                continue
            item_date = published_at.date()
            if oldest is None or item_date < oldest:
                oldest = item_date
        return oldest

    def _fetch_official_news_page(self, page: int) -> dict:
        """Fetch one page from the official AlphaSignal news API."""
        api_url = self.settings.alphasignal_news_api_url
        body = self._build_news_api_body(page)
        logger.info("Fetching AlphaSignal news API page %s: %s", page, api_url)
        content = self._fetch_post(api_url, body)
        raw_payload = json.loads(sanitize_json_payload(content))
        return self._normalize_news_api_payload(raw_payload)

    @traceable_step("alphasignal_fetch_archive_api")
    def fetch_archive_listing(self, start_date: date | None = None) -> str:
        """Fetch archive listing JSON, paginating when needed for backfill."""
        first_payload = self._fetch_official_news_page(1)

        metadata = first_payload.get("metadata") or {}
        total_pages = int(metadata.get("total_pages") or 1)
        all_items: list[dict] = list(extract_api_items(first_payload))

        should_paginate = start_date is not None and total_pages > 1
        if not should_paginate:
            return json.dumps(first_payload)

        page = 2
        while page <= total_pages:
            page_payload = self._fetch_official_news_page(page)
            page_items = extract_api_items(page_payload)
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

    def _fetch_news_article_content(self, article_url: str) -> str:
        """Fetch HTML content from an official AlphaSignal /news/... article page."""
        logger.info("Fetching AlphaSignal news article page: %s", article_url)
        page_content = self._fetch_url(article_url)
        article_html = extract_article_html_from_page(page_content)
        if article_html:
            return article_html
        logger.warning(
            "Could not extract articleDetails from %s; returning rendered page HTML",
            article_url,
        )
        return page_content

    @traceable_step("alphasignal_fetch_newsletter_api")
    def fetch_newsletter_content(self, newsletter_url: str) -> str:
        """Fetch article HTML from an official AlphaSignal /news/... page."""
        if not is_news_article_url(newsletter_url):
            raise ValueError(
                f"Unsupported AlphaSignal URL (expected /news/...): {newsletter_url}"
            )
        return self._fetch_news_article_content(newsletter_url)
