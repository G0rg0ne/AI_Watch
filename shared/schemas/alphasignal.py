"""Pydantic schemas for AlphaSignal agent data structures."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ArchiveEntry(BaseModel):
    """A single publication row from the AlphaSignal archive page."""

    title: str
    url: str
    published_at: datetime
    raw_text: str | None = None


class NewsItem(BaseModel):
    """A news item extracted from a newsletter page."""

    title: str
    summary: str | None = None
    detail_url: str | None = None
    section: Literal["highlight", "detailed"] = "detailed"


class NewsletterDigest(BaseModel):
    """Structured content parsed from one newsletter publication."""

    archive_entry: ArchiveEntry
    highlights: list[NewsItem] = Field(default_factory=list)
    detailed_items: list[NewsItem] = Field(default_factory=list)


class RunResult(BaseModel):
    """Outcome of a daily AlphaSignal agent run."""

    status: Literal["skipped", "processed", "error"]
    message: str
    publication_url: str | None = None
    email_sent: bool = False
    processed_count: int = 0
    publication_urls: list[str] = Field(default_factory=list)
    email_sent_count: int = 0
    failed_count: int = 0
    failed_publication_urls: list[str] = Field(default_factory=list)
