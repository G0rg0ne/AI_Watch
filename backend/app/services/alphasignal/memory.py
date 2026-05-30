"""Persistent memory for processed AlphaSignal publications."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.models.seen_publication import SeenPublication
from backend.app.services.alphasignal.archive_parser import build_dedup_key
from backend.app.services.tracing import traceable_step
from shared.schemas.alphasignal import ArchiveEntry

logger = logging.getLogger(__name__)


class PublicationMemory:
    """SQLite-backed memory for seen archive publications."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @traceable_step("memory_is_seen")
    def is_seen(self, entry: ArchiveEntry) -> bool:
        """Return True if the publication was already processed."""
        dedup_key = build_dedup_key(entry.url, entry.title, entry.published_at)
        exists = (
            self.db.query(SeenPublication)
            .filter(SeenPublication.dedup_key == dedup_key)
            .first()
        )
        return exists is not None

    @traceable_step("memory_mark_seen")
    def mark_seen(self, entry: ArchiveEntry) -> None:
        """Persist a processed publication."""
        dedup_key = build_dedup_key(entry.url, entry.title, entry.published_at)
        existing = (
            self.db.query(SeenPublication)
            .filter(SeenPublication.dedup_key == dedup_key)
            .first()
        )
        if existing:
            logger.info("Publication already marked seen: %s", entry.url)
            return

        record = SeenPublication(
            publication_url=entry.url,
            title=entry.title,
            published_at=entry.published_at,
            seen_at=datetime.utcnow(),
            dedup_key=dedup_key,
        )
        self.db.add(record)
        self.db.commit()
        logger.info("Marked publication as seen: %s", entry.url)

    @traceable_step("memory_find_latest_unseen")
    def find_latest_unseen(self, entries: list[ArchiveEntry]) -> ArchiveEntry | None:
        """Return the newest archive entry that has not been processed."""
        for entry in entries:
            if not self.is_seen(entry):
                logger.info("Found unseen publication: %s (%s)", entry.title, entry.published_at)
                return entry
        logger.info("No unseen publications found")
        return None
