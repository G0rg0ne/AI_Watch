"""Parse AlphaSignal archive page entries."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

from shared.schemas.alphasignal import ArchiveEntry

logger = logging.getLogger(__name__)

ARCHIVE_BASE_URL = "https://alphasignal.ai"
DATE_PATTERN = re.compile(
    r"(?P<date>\d{1,2}/\d{1,2}/\d{4},\s*\d{1,2}:\d{2}:\d{2}\s*[AP]M)\s*$",
    re.IGNORECASE,
)


def build_dedup_key(url: str, title: str, published_at: datetime) -> str:
    """Build a stable deduplication key for a publication."""
    normalized = f"{url}|{title.strip().lower()}|{published_at.isoformat()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class _ArchiveLinkParser(HTMLParser):
    """Extract archive links and visible text from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self._in_anchor = False
        self._current_href: str | None = None
        self._current_text_parts: list[str] = []
        self.entries: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = dict(attrs)
        href = attr_map.get("href")
        if href:
            self._in_anchor = True
            self._current_href = href
            self._current_text_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._in_anchor:
            return
        text = " ".join(part.strip() for part in self._current_text_parts if part.strip())
        if self._current_href and text:
            self.entries.append((self._current_href, text))
        self._in_anchor = False
        self._current_href = None
        self._current_text_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_anchor:
            self._current_text_parts.append(data)


def parse_archive_datetime(raw_date: str) -> datetime:
    """Parse AlphaSignal archive datetime strings."""
    cleaned = raw_date.strip()
    for fmt in ("%m/%d/%Y, %I:%M:%S %p", "%m/%d/%Y, %H:%M:%S"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unable to parse archive date: {raw_date!r}")


def split_title_and_date(text: str) -> tuple[str, datetime]:
    """Split combined archive row text into title and publication datetime."""
    match = DATE_PATTERN.search(text.strip())
    if not match:
        raise ValueError(f"No publication date found in archive text: {text!r}")
    raw_date = match.group("date")
    title = text[: match.start()].strip()
    published_at = parse_archive_datetime(raw_date)
    return title, published_at


def normalize_archive_url(href: str, base_url: str = ARCHIVE_BASE_URL) -> str:
    """Normalize relative archive links to absolute URLs."""
    return urljoin(base_url, href)


def parse_archive_entry_from_text(href: str, text: str) -> ArchiveEntry | None:
    """Parse one archive row from link href and visible text."""
    try:
        title, published_at = split_title_and_date(text)
    except ValueError as exc:
        logger.debug("Skipping archive row: %s", exc)
        return None
    url = normalize_archive_url(href)
    return ArchiveEntry(title=title, url=url, published_at=published_at, raw_text=text)


def parse_archive_entries(content: str) -> list[ArchiveEntry]:
    """
    Parse archive entries from HTML or plain text content.

    Supports HTML anchor tags and plain-text lines containing a publication date.
    """
    entries: list[ArchiveEntry] = []

    if "<a" in content.lower():
        parser = _ArchiveLinkParser()
        parser.feed(content)
        for href, text in parser.entries:
            entry = parse_archive_entry_from_text(href, text)
            if entry:
                entries.append(entry)
    else:
        for line in content.splitlines():
            line = line.strip()
            if not line or not DATE_PATTERN.search(line):
                continue
            entry = parse_archive_entry_from_text("/", line)
            if entry:
                entries.append(entry)

    unique: dict[str, ArchiveEntry] = {}
    for entry in entries:
        unique[entry.url] = entry

    sorted_entries = sorted(unique.values(), key=lambda item: item.published_at, reverse=True)
    logger.info("Parsed %d archive entries", len(sorted_entries))
    return sorted_entries
