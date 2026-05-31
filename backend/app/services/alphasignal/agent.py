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
from shared.schemas.alphasignal import ArchiveEntry, RunResult

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

    def _process_entry(self, entry: ArchiveEntry) -> None:
        """Fetch, summarize, and email one newsletter edition."""
        newsletter_content = self.alphasignal.fetch_newsletter_content(entry.url)
        digest = parse_newsletter(entry, newsletter_content)
        summary = self.summarizer.summarize(digest)
        subject = self.summarizer.build_email_subject(digest)

        footer = (
            f"\n\n---\nSource: {digest.archive_entry.url}\n"
            f"Published: {digest.archive_entry.published_at.isoformat()}"
        )
        self.email_sender.send(subject=subject, body=summary + footer)
        self.memory.mark_seen(entry)

    @traceable_step("alphasignal_agent_run")
    def run(self, trigger: str = "direct") -> RunResult:
        """Execute one full AlphaSignal check cycle."""
        configure_langsmith(self.settings)
        logger.info("Starting AlphaSignal agent run (trigger=%s)", trigger)

        start_date = self.settings.alphasignal_start_date
        archive_content = self.alphasignal.fetch_archive_listing(start_date=start_date)
        archive_entries = parse_archive_entries(
            archive_content,
            base_url=self.settings.alphasignal_base_url,
        )
        if not archive_entries:
            return RunResult(
                status="error",
                message="No archive entries could be parsed from AlphaSignal archive page.",
            )

        unseen_entries = self.memory.find_unseen_since(archive_entries, start_date)
        if not unseen_entries:
            return RunResult(
                status="skipped",
                message="No eligible unseen publications found. No email sent.",
            )

        logger.info(
            "Processing %d eligible unseen newsletter(s) in chronological order",
            len(unseen_entries),
        )

        processed_urls: list[str] = []
        failed_urls: list[str] = []

        for entry in unseen_entries:
            try:
                logger.info("Processing newsletter: %s (%s)", entry.title, entry.url)
                self._process_entry(entry)
                processed_urls.append(entry.url)
            except Exception:
                logger.exception("Failed to process newsletter: %s (%s)", entry.title, entry.url)
                failed_urls.append(entry.url)

        if processed_urls:
            if len(processed_urls) == 1:
                processed_title = next(
                    item.title for item in unseen_entries if item.url == processed_urls[0]
                )
                message = f"Processed and emailed newsletter: {processed_title}"
            else:
                message = f"Processed and emailed {len(processed_urls)} newsletter(s)."
            if failed_urls:
                message += f" {len(failed_urls)} edition(s) failed."
            return RunResult(
                status="processed",
                message=message,
                publication_url=processed_urls[-1],
                email_sent=True,
                processed_count=len(processed_urls),
                publication_urls=processed_urls,
                email_sent_count=len(processed_urls),
                failed_count=len(failed_urls),
                failed_publication_urls=failed_urls,
            )

        return RunResult(
            status="error",
            message=f"Failed to process {len(failed_urls)} eligible newsletter(s).",
            failed_count=len(failed_urls),
            failed_publication_urls=failed_urls,
        )


def run_alphasignal_agent(db: Session, trigger: str = "direct") -> RunResult:
    """Convenience wrapper to run the agent."""
    agent = AlphaSignalAgent(db=db)
    return agent.run(trigger=trigger)
