"""Tests for AlphaSignalClient helpers."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from backend.app.core.config import Settings
from backend.app.services.alphasignal.alphasignal_client import AlphaSignalClient


def _client(**overrides: object) -> AlphaSignalClient:
    settings = Settings(
        openai_api_key="test-key",
        smtp_host="smtp.example.com",
        smtp_user="user",
        smtp_password="pass",
        email_from="from@example.com",
        email_to="to@example.com",
        **overrides,
    )
    return AlphaSignalClient(settings=settings)


def test_build_news_api_body_uses_latest_sort_and_limit() -> None:
    client = _client(alphasignal_archive_limit=12)
    assert client._build_news_api_body(2) == {
        "page": 2,
        "limit": 12,
        "sort": "latest",
        "timeframe": "latest",
    }


def test_normalize_news_api_payload_flattens_official_response() -> None:
    client = _client()
    normalized = client._normalize_news_api_payload(
        {
            "success": True,
            "data": {
                "metadata": {"total_records": 2, "total_pages": 1},
                "data": [{"title": "One"}, {"title": "Two"}],
            },
        }
    )
    assert normalized == {
        "metadata": {"total_records": 2, "total_pages": 1},
        "data": [{"title": "One"}, {"title": "Two"}],
    }


def test_fetch_archive_listing_returns_normalized_json_string() -> None:
    client = _client()
    official_payload = {
        "success": True,
        "data": {
            "metadata": {"total_records": 1, "total_pages": 1, "current_page": 1, "limit": 10},
            "data": [
                {
                    "news_id": "news-1",
                    "title": "Test Article",
                    "publish_time": "2026-06-03T05:12:32.123Z",
                }
            ],
        },
    }

    with patch.object(client, "_fetch_post", return_value=json.dumps(official_payload)):
        content = client.fetch_archive_listing()

    payload = json.loads(content)
    assert payload["metadata"]["total_records"] == 1
    assert payload["data"][0]["title"] == "Test Article"


def test_fetch_newsletter_content_rejects_non_news_urls() -> None:
    client = _client()
    with pytest.raises(ValueError, match="expected /news/"):
        client.fetch_newsletter_content("https://alphasignal.ai/email/campaign-1")


def test_fetch_newsletter_content_fetches_news_detail_api() -> None:
    client = _client()
    article_url = "https://alphasignal.ai/news/test-article"
    detail_payload = {
        "success": True,
        "data": {
            "articleDetails": {
                "summary_html": "<ul><li>Takeaway</li></ul>",
                "html_text": "<p>Article body</p>",
            }
        },
    }

    with patch.object(client, "_fetch_url", return_value=json.dumps(detail_payload)) as mock_fetch:
        content = client.fetch_newsletter_content(article_url)

    assert "<p>Article body</p>" in content
    assert "<li>Takeaway</li>" in content
    mock_fetch.assert_called_once_with(
        "https://api.alphasignal.ai/api/news/detail?slug=test-article"
    )
