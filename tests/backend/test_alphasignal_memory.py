"""Tests for publication memory deduplication and batch agent runs."""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import Settings
from backend.app.db.database import Base
from backend.app.services.alphasignal.agent import AlphaSignalAgent, run_alphasignal_agent
from backend.app.services.alphasignal.archive_parser import parse_archive_entries
from backend.app.services.alphasignal.memory import PublicationMemory
from shared.schemas.alphasignal import ArchiveEntry, RunResult


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _entry(url: str, title: str, day: int, month: int = 5) -> ArchiveEntry:
    return ArchiveEntry(
        title=title,
        url=url,
        published_at=datetime(2026, month, day, 12, 0, 0),
    )


def _test_settings(**overrides) -> Settings:
    defaults = {
        "openai_api_key": "test-openai-key",
        "smtp_host": "smtp.test.local",
        "smtp_user": "test-user",
        "smtp_password": "test-password",
        "email_from": "from@test.local",
        "email_to": "to@test.local",
        "database_url": "sqlite:///:memory:",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_memory_marks_and_detects_seen_publications(db_session) -> None:
    memory = PublicationMemory(db_session)
    entry = _entry("https://alphasignal.ai/newsletter/a", "Newsletter A", 29)

    assert memory.is_seen(entry) is False
    memory.mark_seen(entry)
    assert memory.is_seen(entry) is True


def test_find_latest_unseen_returns_newest_unprocessed(db_session) -> None:
    memory = PublicationMemory(db_session)
    newest = _entry("https://alphasignal.ai/newsletter/new", "New", 29)
    older = _entry("https://alphasignal.ai/newsletter/old", "Old", 28)
    memory.mark_seen(older)

    result = memory.find_latest_unseen([newest, older])
    assert result == newest


def test_find_latest_unseen_returns_none_when_all_seen(db_session) -> None:
    memory = PublicationMemory(db_session)
    entries = [
        _entry("https://alphasignal.ai/newsletter/a", "A", 29),
        _entry("https://alphasignal.ai/newsletter/b", "B", 28),
    ]
    for entry in entries:
        memory.mark_seen(entry)

    assert memory.find_latest_unseen(entries) is None


def test_find_unseen_since_returns_all_unseen_oldest_first(db_session) -> None:
    memory = PublicationMemory(db_session)
    oldest = _entry("https://alphasignal.ai/newsletter/old", "Old", 28)
    middle = _entry("https://alphasignal.ai/newsletter/mid", "Mid", 29)
    newest = _entry("https://alphasignal.ai/newsletter/new", "New", 30)
    memory.mark_seen(middle)

    result = memory.find_unseen_since([newest, middle, oldest], start_date=date(2026, 5, 28))

    assert result == [oldest, newest]


def test_find_unseen_since_respects_start_date_cutoff(db_session) -> None:
    memory = PublicationMemory(db_session)
    before_cutoff = _entry(
        "https://alphasignal.ai/newsletter/april",
        "April",
        day=30,
        month=4,
    )
    after_cutoff = _entry("https://alphasignal.ai/newsletter/may", "May", 1)

    result = memory.find_unseen_since(
        [after_cutoff, before_cutoff],
        start_date=date(2026, 5, 1),
    )

    assert result == [after_cutoff]


def test_find_unseen_since_excludes_seen_entries(db_session) -> None:
    memory = PublicationMemory(db_session)
    seen = _entry("https://alphasignal.ai/newsletter/seen", "Seen", 28)
    unseen = _entry("https://alphasignal.ai/newsletter/unseen", "Unseen", 29)
    memory.mark_seen(seen)

    result = memory.find_unseen_since([unseen, seen])

    assert result == [unseen]


def test_settings_parses_alphasignal_start_date() -> None:
    settings = _test_settings(alphasignal_start_date="2026-05-01")
    assert settings.alphasignal_start_date == date(2026, 5, 1)


def test_settings_treats_blank_start_date_as_none() -> None:
    settings = _test_settings(alphasignal_start_date="")
    assert settings.alphasignal_start_date is None


def test_run_alphasignal_agent_passes_trace_trigger(db_session) -> None:
    with (
        patch.object(AlphaSignalAgent, "__init__", return_value=None) as mock_init,
        patch.object(
            AlphaSignalAgent,
            "run",
            return_value=RunResult(status="skipped", message="No new publication."),
        ) as mock_run,
    ):
        result = run_alphasignal_agent(db_session, trigger="manual_api")

    assert result.status == "skipped"
    mock_init.assert_called_once_with(db=db_session)
    mock_run.assert_called_once_with(trigger="manual_api")


def test_agent_skips_when_publication_already_seen(db_session) -> None:
    entry = _entry("https://alphasignal.ai/newsletter/a", "Already seen", 29)
    archive_html = (
        '<a href="/newsletter/a"><div>Already seen 5/29/2026, 12:00:00 PM</div></a>'
    )

    alphasignal = MagicMock()
    alphasignal.fetch_archive_listing.return_value = archive_html

    memory = PublicationMemory(db_session)
    memory.mark_seen(entry)

    agent = AlphaSignalAgent(db_session, alphasignal_client=alphasignal)
    result = agent.run()

    assert result.status == "skipped"
    assert result.email_sent is False
    alphasignal.fetch_archive_listing.assert_called_once_with(start_date=None)
    alphasignal.fetch_newsletter_content.assert_not_called()


@patch("backend.app.services.alphasignal.agent.SmtpEmailSender")
@patch("backend.app.services.alphasignal.agent.NewsletterSummarizer")
def test_agent_processes_new_publication(
    mock_summarizer_cls,
    mock_email_sender_cls,
    db_session,
) -> None:
    archive_html = """
    <a href="/newsletter/new-one">
      <div>🤖 Brand new newsletter 5/30/2026, 8:00:00 AM</div>
    </a>
    """
    newsletter_content = """
    # In Today's Signal
    Major AI launch today
    # The Rest of Today's Signal
    ## Detailed story
    This is the resume of the detailed story.
    https://example.com/story
    """

    alphasignal = MagicMock()
    alphasignal.fetch_archive_listing.return_value = archive_html
    alphasignal.fetch_newsletter_content.return_value = newsletter_content

    summarizer = MagicMock()
    summarizer.summarize.return_value = "Executive summary"
    summarizer.build_email_subject.return_value = "AlphaSignal Digest"
    mock_summarizer_cls.return_value = summarizer

    email_sender = MagicMock()
    mock_email_sender_cls.return_value = email_sender

    agent = AlphaSignalAgent(db_session, alphasignal_client=alphasignal)
    result = agent.run()

    assert result.status == "processed"
    assert result.email_sent is True
    assert result.processed_count == 1
    assert result.email_sent_count == 1
    email_sender.send.assert_called_once()
    parsed_entries = parse_archive_entries(archive_html)
    memory = PublicationMemory(db_session)
    assert memory.is_seen(parsed_entries[0])


@patch("backend.app.services.alphasignal.agent.SmtpEmailSender")
@patch("backend.app.services.alphasignal.agent.NewsletterSummarizer")
def test_agent_processes_multiple_unseen_newsletters_in_one_run(
    mock_summarizer_cls,
    mock_email_sender_cls,
    db_session,
) -> None:
    archive_html = """
    <a href="/newsletter/newer">
      <div>🤖 Newer newsletter 5/30/2026, 8:00:00 AM</div>
    </a>
    <a href="/newsletter/older">
      <div>🤖 Older newsletter 5/29/2026, 8:00:00 AM</div>
    </a>
    """
    newsletter_content = """
    # In Today's Signal
    Major AI launch today
    # The Rest of Today's Signal
    ## Detailed story
    This is the resume of the detailed story.
    https://example.com/story
    """

    alphasignal = MagicMock()
    alphasignal.fetch_archive_listing.return_value = archive_html
    alphasignal.fetch_newsletter_content.return_value = newsletter_content

    summarizer = MagicMock()
    summarizer.summarize.return_value = "Executive summary"
    summarizer.build_email_subject.side_effect = ["Subject A", "Subject B"]
    mock_summarizer_cls.return_value = summarizer

    email_sender = MagicMock()
    mock_email_sender_cls.return_value = email_sender

    agent = AlphaSignalAgent(db_session, alphasignal_client=alphasignal)
    result = agent.run()

    assert result.status == "processed"
    assert result.processed_count == 2
    assert result.email_sent_count == 2
    assert email_sender.send.call_count == 2

    parsed_entries = parse_archive_entries(archive_html)
    memory = PublicationMemory(db_session)
    for entry in parsed_entries:
        assert memory.is_seen(entry)

    call_urls = [call.args[0] for call in alphasignal.fetch_newsletter_content.call_args_list]
    older_url = next(entry.url for entry in parsed_entries if "older" in entry.url)
    newer_url = next(entry.url for entry in parsed_entries if "newer" in entry.url)
    assert call_urls == [older_url, newer_url]


@patch("backend.app.services.alphasignal.agent.SmtpEmailSender")
@patch("backend.app.services.alphasignal.agent.NewsletterSummarizer")
def test_agent_skips_editions_before_start_date(
    mock_summarizer_cls,
    mock_email_sender_cls,
    db_session,
) -> None:
    archive_html = """
    <a href="/newsletter/may">
      <div>🤖 May newsletter 5/2/2026, 8:00:00 AM</div>
    </a>
    <a href="/newsletter/april">
      <div>🤖 April newsletter 4/30/2026, 8:00:00 AM</div>
    </a>
    """
    newsletter_content = """
    # In Today's Signal
    Major AI launch today
    """

    alphasignal = MagicMock()
    alphasignal.fetch_archive_listing.return_value = archive_html
    alphasignal.fetch_newsletter_content.return_value = newsletter_content

    summarizer = MagicMock()
    summarizer.summarize.return_value = "Executive summary"
    summarizer.build_email_subject.return_value = "AlphaSignal Digest"
    mock_summarizer_cls.return_value = summarizer

    email_sender = MagicMock()
    mock_email_sender_cls.return_value = email_sender

    settings = _test_settings(alphasignal_start_date=date(2026, 5, 1))
    agent = AlphaSignalAgent(
        db_session,
        settings=settings,
        alphasignal_client=alphasignal,
    )
    result = agent.run()

    assert result.status == "processed"
    assert result.processed_count == 1
    email_sender.send.assert_called_once()
    alphasignal.fetch_archive_listing.assert_called_once_with(start_date=date(2026, 5, 1))

    parsed_entries = parse_archive_entries(archive_html)
    memory = PublicationMemory(db_session)
    may_entry = next(entry for entry in parsed_entries if "may" in entry.url)
    april_entry = next(entry for entry in parsed_entries if "april" in entry.url)
    assert memory.is_seen(may_entry)
    assert memory.is_seen(april_entry) is False


@patch("backend.app.services.alphasignal.agent.SmtpEmailSender")
@patch("backend.app.services.alphasignal.agent.NewsletterSummarizer")
def test_agent_processes_only_unseen_entries_when_mixed(
    mock_summarizer_cls,
    mock_email_sender_cls,
    db_session,
) -> None:
    archive_html = """
    <a href="/newsletter/seen">
      <div>🤖 Seen newsletter 5/30/2026, 8:00:00 AM</div>
    </a>
    <a href="/newsletter/unseen">
      <div>🤖 Unseen newsletter 5/29/2026, 8:00:00 AM</div>
    </a>
    """
    newsletter_content = """
    # In Today's Signal
    Major AI launch today
    """

    parsed_entries = parse_archive_entries(archive_html)
    seen_entry = next(entry for entry in parsed_entries if "seen" in entry.url)
    PublicationMemory(db_session).mark_seen(seen_entry)

    alphasignal = MagicMock()
    alphasignal.fetch_archive_listing.return_value = archive_html
    alphasignal.fetch_newsletter_content.return_value = newsletter_content

    summarizer = MagicMock()
    summarizer.summarize.return_value = "Executive summary"
    summarizer.build_email_subject.return_value = "AlphaSignal Digest"
    mock_summarizer_cls.return_value = summarizer

    email_sender = MagicMock()
    mock_email_sender_cls.return_value = email_sender

    agent = AlphaSignalAgent(db_session, alphasignal_client=alphasignal)
    result = agent.run()

    assert result.status == "processed"
    assert result.processed_count == 1
    email_sender.send.assert_called_once()

    unseen_entry = next(entry for entry in parsed_entries if "unseen" in entry.url)
    memory = PublicationMemory(db_session)
    assert memory.is_seen(unseen_entry)
    assert memory.is_seen(seen_entry)


@patch("backend.app.services.alphasignal.agent.SmtpEmailSender")
@patch("backend.app.services.alphasignal.agent.NewsletterSummarizer")
def test_agent_continues_after_partial_failure(
    mock_summarizer_cls,
    mock_email_sender_cls,
    db_session,
) -> None:
    archive_html = """
    <a href="/newsletter/fail">
      <div>🤖 Failing newsletter 5/29/2026, 8:00:00 AM</div>
    </a>
    <a href="/newsletter/success">
      <div>🤖 Success newsletter 5/30/2026, 8:00:00 AM</div>
    </a>
    """
    newsletter_content = """
    # In Today's Signal
    Major AI launch today
    """

    parsed_entries = parse_archive_entries(archive_html)
    fail_entry = next(entry for entry in parsed_entries if "fail" in entry.url)
    success_entry = next(entry for entry in parsed_entries if "success" in entry.url)

    alphasignal = MagicMock()
    alphasignal.fetch_archive_listing.return_value = archive_html

    def fetch_side_effect(url: str) -> str:
        if url == fail_entry.url:
            raise RuntimeError("fetch failed")
        return newsletter_content

    alphasignal.fetch_newsletter_content.side_effect = fetch_side_effect

    summarizer = MagicMock()
    summarizer.summarize.return_value = "Executive summary"
    summarizer.build_email_subject.return_value = "AlphaSignal Digest"
    mock_summarizer_cls.return_value = summarizer

    email_sender = MagicMock()
    mock_email_sender_cls.return_value = email_sender

    agent = AlphaSignalAgent(db_session, alphasignal_client=alphasignal)
    result = agent.run()

    assert result.status == "processed"
    assert result.processed_count == 1
    assert result.failed_count == 1
    assert result.publication_urls == [success_entry.url]
    assert result.failed_publication_urls == [fail_entry.url]
    email_sender.send.assert_called_once()

    memory = PublicationMemory(db_session)
    assert memory.is_seen(fail_entry) is False
    assert memory.is_seen(success_entry)
