"""Tests for AlphaSignal fetch mode routing (direct, browserbase, auto)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from backend.app.core.config import Settings
from backend.app.services.alphasignal.alphasignal_client import AlphaSignalClient
from backend.app.services.alphasignal.browserbase_fetcher import (
    BrowserbaseFetchError,
    BrowserbaseFetcher,
)

ARCHIVE_JSON = (
    '{"metadata":{"total_records":1,"total_pages":1,"current_page":1,"limit":10},'
    '"data":[{"_id":"abc","subject":"Test","timestamp":"2026-06-03T05:12:32.123Z",'
    '"as_campaign_id":"campaign-1"}]}'
)
NEWSLETTER_JSON = '{"data":{"html":"<p>Newsletter body</p>"}}'


def _settings(**overrides: object) -> Settings:
    base = {
        "openai_api_key": "test-key",
        "smtp_host": "smtp.example.com",
        "smtp_user": "user",
        "smtp_password": "pass",
        "email_from": "from@example.com",
        "email_to": "to@example.com",
    }
    base.update(overrides)
    return Settings(**base)


def test_fetch_url_direct_mode_uses_httpx() -> None:
    client = AlphaSignalClient(settings=_settings(alphasignal_fetch_mode="direct"))
    with patch("backend.app.services.alphasignal.alphasignal_client.httpx.get") as mock_get:
        mock_response = MagicMock()
        mock_response.text = ARCHIVE_JSON
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        content = client._fetch_url("https://alphasignal.ai/api/archive?page=1&limit=10")

    assert content == ARCHIVE_JSON
    mock_get.assert_called_once()


def test_fetch_archive_listing_browserbase_mode_delegates() -> None:
    mock_fetcher = MagicMock(spec=BrowserbaseFetcher)
    mock_fetcher.fetch_url.return_value = ARCHIVE_JSON
    client = AlphaSignalClient(
        settings=_settings(alphasignal_fetch_mode="browserbase"),
        browserbase_fetcher=mock_fetcher,
    )

    content = client.fetch_archive_listing()

    assert content == ARCHIVE_JSON
    mock_fetcher.fetch_url.assert_called_once_with(
        "https://alphasignal.ai/api/archive?page=1&limit=10"
    )


def test_fetch_newsletter_content_browserbase_mode_delegates() -> None:
    mock_fetcher = MagicMock(spec=BrowserbaseFetcher)
    mock_fetcher.fetch_url.return_value = NEWSLETTER_JSON
    client = AlphaSignalClient(
        settings=_settings(alphasignal_fetch_mode="browserbase"),
        browserbase_fetcher=mock_fetcher,
    )

    content = client.fetch_newsletter_content(
        "https://alphasignal.ai/email/campaign-1"
    )

    assert content == "<p>Newsletter body</p>"
    mock_fetcher.fetch_url.assert_called_once_with(
        "https://alphasignal.ai/api/archive/campaign-1"
    )


def test_fetch_url_auto_mode_falls_back_to_browserbase_on_403() -> None:
    mock_fetcher = MagicMock(spec=BrowserbaseFetcher)
    mock_fetcher.fetch_url.return_value = ARCHIVE_JSON
    client = AlphaSignalClient(
        settings=_settings(alphasignal_fetch_mode="auto"),
        browserbase_fetcher=mock_fetcher,
    )

    request = httpx.Request("GET", "https://alphasignal.ai/api/archive?page=1&limit=10")
    response = httpx.Response(403, request=request)

    with patch("backend.app.services.alphasignal.alphasignal_client.httpx.get") as mock_get:
        mock_get.return_value = response
        content = client._fetch_url("https://alphasignal.ai/api/archive?page=1&limit=10")

    assert content == ARCHIVE_JSON
    mock_fetcher.fetch_url.assert_called_once()


def test_fetch_url_auto_mode_reraises_non_403_errors() -> None:
    mock_fetcher = MagicMock(spec=BrowserbaseFetcher)
    client = AlphaSignalClient(
        settings=_settings(alphasignal_fetch_mode="auto"),
        browserbase_fetcher=mock_fetcher,
    )

    request = httpx.Request("GET", "https://alphasignal.ai/api/archive?page=1&limit=10")
    response = httpx.Response(500, request=request)

    with patch("backend.app.services.alphasignal.alphasignal_client.httpx.get") as mock_get:
        mock_get.return_value = response
        with pytest.raises(httpx.HTTPStatusError):
            client._fetch_url("https://alphasignal.ai/api/archive?page=1&limit=10")

    mock_fetcher.fetch_url.assert_not_called()


def test_browserbase_fetcher_requires_api_key() -> None:
    fetcher = BrowserbaseFetcher(
        settings=_settings(
            alphasignal_fetch_mode="browserbase",
            browserbase_api_key=None,
        )
    )

    with pytest.raises(BrowserbaseFetchError, match="BROWSERBASE_API_KEY"):
        fetcher.fetch_url("https://alphasignal.ai/api/archive?page=1&limit=10")


def test_browserbase_fetcher_raises_on_403_response() -> None:
    fetcher = BrowserbaseFetcher(
        settings=_settings(
            alphasignal_fetch_mode="browserbase",
            browserbase_api_key="bb-test-key",
            browserbase_project_id="proj-123",
        )
    )

    mock_session = MagicMock()
    mock_session.id = "session-1"
    mock_session.connect_url = "wss://connect.browserbase.com/devtools"

    mock_page = MagicMock()
    mock_page.evaluate.return_value = {
        "status": 403,
        "url": "https://alphasignal.ai/api/archive?page=1&limit=10",
        "text": "Forbidden",
    }

    mock_context = MagicMock()
    mock_context.pages = [mock_page]

    mock_browser = MagicMock()
    mock_browser.contexts = [mock_context]

    mock_playwright = MagicMock()
    mock_playwright.chromium.connect_over_cdp.return_value = mock_browser

    with patch("browserbase.Browserbase") as mock_bb_cls:
        mock_bb_cls.return_value.sessions.create.return_value = mock_session
        with patch(
            "backend.app.services.alphasignal.browserbase_fetcher.sync_playwright"
        ) as mock_sync_playwright:
            mock_sync_playwright.return_value.start.return_value = mock_playwright
            with pytest.raises(BrowserbaseFetchError, match="403 Forbidden via Browserbase"):
                fetcher.fetch_url("https://alphasignal.ai/api/archive?page=1&limit=10")

    mock_bb_cls.return_value.sessions.create.assert_called_once_with(
        timeout=120,
        project_id="proj-123",
        proxies=True,
    )
