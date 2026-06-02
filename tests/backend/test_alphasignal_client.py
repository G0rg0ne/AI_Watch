"""Tests for AlphaSignalClient archive URL building."""

from __future__ import annotations

from backend.app.core.config import Settings
from backend.app.services.alphasignal.alphasignal_client import AlphaSignalClient


def _client(archive_api_url: str, archive_limit: int = 10) -> AlphaSignalClient:
    settings = Settings(
        openai_api_key="test-key",
        smtp_host="smtp.example.com",
        smtp_user="user",
        smtp_password="pass",
        email_from="from@example.com",
        email_to="to@example.com",
        alphasignal_archive_api_url=archive_api_url,
        alphasignal_archive_limit=archive_limit,
    )
    return AlphaSignalClient(settings=settings)


def test_build_archive_api_url_preserves_host_path_and_limit() -> None:
    client = _client("https://cdn.example.com/api/archive?page=1&limit=25")
    assert client._build_archive_api_url(1) == "https://cdn.example.com/api/archive?page=1&limit=25"
    assert client._build_archive_api_url(3) == "https://cdn.example.com/api/archive?page=3&limit=25"


def test_build_archive_api_url_preserves_extra_query_params() -> None:
    client = _client("https://alphasignal.ai/api/archive?page=1&limit=10&sort=desc")
    assert client._build_archive_api_url(2) == "https://alphasignal.ai/api/archive?page=2&limit=10&sort=desc"


def test_build_archive_api_url_uses_archive_limit_when_missing_from_url() -> None:
    client = _client("https://alphasignal.ai/api/archive?page=1", archive_limit=50)
    assert client._build_archive_api_url(1) == "https://alphasignal.ai/api/archive?page=1&limit=50"
