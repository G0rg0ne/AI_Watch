"""Tests for publication memory deduplication."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.database import Base
from backend.app.services.alphasignal.agent import AlphaSignalAgent
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


def _entry(url: str, title: str, day: int) -> ArchiveEntry:
    return ArchiveEntry(
        title=title,
        url=url,
        published_at=datetime(2026, 5, day, 12, 0, 0),
    )


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


def test_agent_skips_when_publication_already_seen(db_session) -> None:
    entry = _entry("https://alphasignal.ai/newsletter/a", "Already seen", 29)
    archive_html = (
        '<a href="/newsletter/a"><div>Already seen 5/29/2026, 12:00:00 PM</div></a>'
    )

    tavily = MagicMock()
    tavily.fetch_archive_listing.return_value = archive_html

    memory = PublicationMemory(db_session)
    memory.mark_seen(entry)

    agent = AlphaSignalAgent(db_session, tavily_client=tavily)
    result = agent.run()

    assert result.status == "skipped"
    assert result.email_sent is False
    tavily.fetch_newsletter_content.assert_not_called()


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

    tavily = MagicMock()
    tavily.fetch_archive_listing.return_value = archive_html
    tavily.fetch_newsletter_content.return_value = newsletter_content

    summarizer = MagicMock()
    summarizer.summarize.return_value = "Executive summary"
    summarizer.build_email_subject.return_value = "AlphaSignal Digest"
    mock_summarizer_cls.return_value = summarizer

    email_sender = MagicMock()
    mock_email_sender_cls.return_value = email_sender

    agent = AlphaSignalAgent(db_session, tavily_client=tavily)
    result = agent.run()

    assert result.status == "processed"
    assert result.email_sent is True
    email_sender.send.assert_called_once()
    parsed_entries = parse_archive_entries(archive_html)
    memory = PublicationMemory(db_session)
    assert memory.is_seen(parsed_entries[0])
