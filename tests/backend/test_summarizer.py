"""Tests for NewsletterSummarizer OpenAI integration."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from langchain_core.prompts import ChatPromptTemplate

from backend.app.core.config import Settings
from backend.app.services.alphasignal.summarizer import NewsletterSummarizer
from shared.schemas.alphasignal import ArchiveEntry, NewsletterDigest


def _test_settings(**overrides: object) -> Settings:
    base = {
        "openai_api_key": "test-openai-key",
        "openai_model": "gpt-4o-mini",
        "smtp_host": "smtp.test.local",
        "smtp_user": "test-user",
        "smtp_password": "test-password",
        "email_from": "from@test.local",
        "email_to": "to@test.local",
        "langsmith_summarizer_prompt": "alphasignal-newsletter-summarizer:prod",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _sample_digest() -> NewsletterDigest:
    entry = ArchiveEntry(
        title="Test Newsletter",
        url="https://alphasignal.ai/news/test-newsletter",
        published_at=datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc),
    )
    return NewsletterDigest(archive_entry=entry)


def _mock_langsmith_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            ("system", "You are an AI/ML news analyst."),
            ("user", "Summarize this newsletter.\n\n{newsletter_payload}"),
        ]
    )


def _patch_langsmith_prompt(mock_client_cls: MagicMock) -> MagicMock:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.pull_prompt.return_value = _mock_langsmith_prompt()
    return mock_client


@patch("backend.app.services.alphasignal.summarizer.Client")
@patch(
    "backend.app.services.alphasignal.summarizer.wrap_openai",
    side_effect=lambda client: client,
)
@patch("backend.app.services.alphasignal.summarizer.OpenAI")
def test_summarizer_wraps_openai_client(
    mock_openai_cls: MagicMock,
    mock_wrap: MagicMock,
    mock_client_cls: MagicMock,
) -> None:
    mock_openai_cls.return_value = MagicMock()
    _patch_langsmith_prompt(mock_client_cls)
    settings = _test_settings()

    NewsletterSummarizer(settings=settings)

    mock_openai_cls.assert_called_once_with(api_key="test-openai-key")
    mock_wrap.assert_called_once_with(mock_openai_cls.return_value)


@patch("backend.app.services.alphasignal.summarizer.Client")
@patch(
    "backend.app.services.alphasignal.summarizer.wrap_openai",
    side_effect=lambda client: client,
)
@patch("backend.app.services.alphasignal.summarizer.OpenAI")
def test_summarize_pulls_configured_langsmith_prompt(
    mock_openai_cls: MagicMock,
    _mock_wrap: MagicMock,
    mock_client_cls: MagicMock,
) -> None:
    mock_client = _patch_langsmith_prompt(mock_client_cls)
    mock_openai = MagicMock()
    mock_openai_cls.return_value = mock_openai
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Executive summary body"
    mock_openai.chat.completions.create.return_value = mock_response

    settings = _test_settings(
        langsmith_summarizer_prompt="alphasignal-newsletter-summarizer:staging"
    )
    summarizer = NewsletterSummarizer(settings=settings)
    result = summarizer.summarize(_sample_digest())

    assert result == "Executive summary body"
    mock_client.pull_prompt.assert_called_once_with(
        "alphasignal-newsletter-summarizer:staging"
    )


@patch("backend.app.services.alphasignal.summarizer.Client")
@patch(
    "backend.app.services.alphasignal.summarizer.wrap_openai",
    side_effect=lambda client: client,
)
@patch("backend.app.services.alphasignal.summarizer.OpenAI")
def test_summarize_uses_configured_model_and_langsmith_messages(
    mock_openai_cls: MagicMock,
    _mock_wrap: MagicMock,
    mock_client_cls: MagicMock,
) -> None:
    _patch_langsmith_prompt(mock_client_cls)
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Executive summary body"
    mock_client.chat.completions.create.return_value = mock_response

    settings = _test_settings(openai_model="gpt-4o-mini-custom")
    summarizer = NewsletterSummarizer(settings=settings)
    digest = _sample_digest()

    result = summarizer.summarize(digest)

    assert result == "Executive summary body"
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o-mini-custom"
    assert call_kwargs["temperature"] == 0.3
    messages = call_kwargs["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are an AI/ML news analyst."
    assert messages[1]["role"] == "user"
    assert "Test Newsletter" in messages[1]["content"]
    assert digest.archive_entry.url in messages[1]["content"]


@patch("backend.app.services.alphasignal.summarizer.Client")
@patch(
    "backend.app.services.alphasignal.summarizer.wrap_openai",
    side_effect=lambda client: client,
)
@patch("backend.app.services.alphasignal.summarizer.OpenAI")
def test_summarize_raises_on_empty_response(
    mock_openai_cls: MagicMock,
    _mock_wrap: MagicMock,
    mock_client_cls: MagicMock,
) -> None:
    _patch_langsmith_prompt(mock_client_cls)
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "   "
    mock_client.chat.completions.create.return_value = mock_response

    summarizer = NewsletterSummarizer(settings=_test_settings())

    try:
        summarizer.summarize(_sample_digest())
    except RuntimeError as exc:
        assert "empty summary" in str(exc).lower()
    else:
        raise AssertionError("Expected RuntimeError for empty OpenAI response")
