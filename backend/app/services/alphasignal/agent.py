"""Orchestrates the AlphaSignal daily agent workflow."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.services.alphasignal.archive_parser import parse_archive_entries
from backend.app.services.alphasignal.email_sender import SmtpEmailSender
from backend.app.services.alphasignal.memory import PublicationMemory
from backend.app.services.alphasignal.newsletter_parser import parse_newsletter
from backend.app.services.alphasignal.summarizer import NewsletterSummarizer
from backend.app.services.alphasignal.alphasignal_client import AlphaSignalClient
from backend.app.services.tracing import configure_langsmith, traceable_step
from shared.schemas.alphasignal import RunResult

logger = logging.getLogger(__name__)


class AlphaSignalAgent:
    """Daily agent that checks AlphaSignal and emails new publications."""

    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        alphasignal_client: AlphaSignalClient | None = None,
        summarizer: NewsletterSummarizer | None = None,
        email_sender: SmtpEmailSender | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db
        self.alphasignal = alphasignal_client or AlphaSignalClient(self.settings)
        self.memory = PublicationMemory(db)
        self.summarizer = summarizer or NewsletterSummarizer(self.settings)
        self.email_sender = email_sender or SmtpEmailSender(self.settings)

    @traceable_step("alphasignal_agent_run")
    def run(self, trigger: str = "direct") -> RunResult:
        """Execute one full AlphaSignal check cycle."""
        configure_langsmith(self.settings)
        logger.info("Starting AlphaSignal agent run (trigger=%s)", trigger)

        archive_content = self.alphasignal.fetch_archive_listing()
        archive_entries = parse_archive_entries(
            archive_content,
            base_url=self.settings.alphasignal_base_url,
        )
        if not archive_entries:
            return RunResult(
                status="error",
                message="No archive entries could be parsed from AlphaSignal archive page.",
            )

        unseen_entry = self.memory.find_latest_unseen(archive_entries)
        if unseen_entry is None:
            return RunResult(
                status="skipped",
                message="Latest publication already processed. No email sent.",
            )

        newsletter_content = self.alphasignal.fetch_newsletter_content(unseen_entry.url)

        digest = parse_newsletter(unseen_entry, newsletter_content)
        summary = self.summarizer.summarize(digest)
        subject = self.summarizer.build_email_subject(digest)

        footer = (
            f"\n\n---\nSource: {digest.archive_entry.url}\n"
            f"Published: {digest.archive_entry.published_at.isoformat()}"
        )
        self.email_sender.send(subject=subject, body=summary + footer)
        self.memory.mark_seen(unseen_entry)

        return RunResult(
            status="processed",
            message=f"Processed and emailed newsletter: {unseen_entry.title}",
            publication_url=unseen_entry.url,
            email_sent=True,
        )


def run_alphasignal_agent(db: Session, trigger: str = "direct") -> RunResult:
    """Convenience wrapper to run the agent."""
    agent = AlphaSignalAgent(db=db)
    return agent.run(trigger=trigger)
