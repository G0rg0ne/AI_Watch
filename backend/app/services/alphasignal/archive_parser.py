"""Parse AlphaSignal archive page entries."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

from shared.schemas.alphasignal import ArchiveEntry

logger = logging.getLogger(__name__)

ARCHIVE_BASE_URL = "https://alphasignal.ai"
ARCHIVE_API_PATH = "/api/archive"
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


def build_email_url(campaign_id: str, base_url: str = ARCHIVE_BASE_URL) -> str:
    """Build the public newsletter URL from an AlphaSignal campaign id."""
    return urljoin(base_url, f"/email/{campaign_id}")


def build_newsletter_api_url(campaign_id: str, base_url: str = ARCHIVE_BASE_URL) -> str:
    """Build the JSON API URL for one newsletter publication."""
    return urljoin(base_url, f"{ARCHIVE_API_PATH}/{campaign_id}")


def extract_campaign_id(newsletter_url: str) -> str | None:
    """Extract a campaign id from an AlphaSignal /email/{id} URL."""
    match = re.search(r"/email/([A-Za-z0-9]+)", newsletter_url)
    if match:
        return match.group(1)
    return None


def parse_api_timestamp(raw_timestamp: str) -> datetime:
    """Parse ISO timestamps returned by the AlphaSignal archive API."""
    normalized = raw_timestamp.replace("Z", "+00:00")
    published_at = datetime.fromisoformat(normalized)
    if published_at.tzinfo is not None:
        published_at = published_at.replace(tzinfo=None)
    return published_at


def sanitize_tavily_json(content: str) -> str:
    """Undo markdown escaping Tavily sometimes adds to extracted JSON payloads."""
    if not content.strip().startswith("{"):
        return content
    return content.replace("\\_", "_")


def parse_archive_api_json(
    content: str,
    base_url: str = ARCHIVE_BASE_URL,
) -> list[ArchiveEntry]:
    """Parse archive entries from the AlphaSignal JSON API response."""
    payload = json.loads(sanitize_tavily_json(content))
    items = payload.get("data") or []
    entries: list[ArchiveEntry] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        campaign_id = item.get("as_campaign_id")
        subject = item.get("subject")
        timestamp = item.get("timestamp")
        if not campaign_id or not subject or not timestamp:
            continue
        try:
            published_at = parse_api_timestamp(str(timestamp))
        except ValueError as exc:
            logger.debug("Skipping API archive row: %s", exc)
            continue
        entries.append(
            ArchiveEntry(
                title=str(subject).strip(),
                url=build_email_url(str(campaign_id), base_url),
                published_at=published_at,
                raw_text=str(subject).strip(),
            )
        )

    sorted_entries = sorted(entries, key=lambda item: item.published_at, reverse=True)
    logger.info("Parsed %d archive entries from API JSON", len(sorted_entries))
    return sorted_entries


def parse_archive_entry_from_text(href: str, text: str) -> ArchiveEntry | None:
    """Parse one archive row from link href and visible text."""
    try:
        title, published_at = split_title_and_date(text)
    except ValueError as exc:
        logger.debug("Skipping archive row: %s", exc)
        return None
    url = normalize_archive_url(href)
    return ArchiveEntry(title=title, url=url, published_at=published_at, raw_text=text)


def parse_archive_entries(content: str, base_url: str = ARCHIVE_BASE_URL) -> list[ArchiveEntry]:
    """
    Parse archive entries from API JSON, HTML, or plain text content.

    Supports AlphaSignal API JSON, HTML anchor tags, and plain-text lines
    containing a publication date.
    """
    stripped = content.strip()
    if stripped.startswith("{"):
        try:
            api_entries = parse_archive_api_json(stripped, base_url=base_url)
            if api_entries:
                return api_entries
        except json.JSONDecodeError:
            logger.debug("Content looked like JSON but could not be parsed as archive API data")

    entries: list[ArchiveEntry] = []

    if "<a" in stripped.lower():
        parser = _ArchiveLinkParser()
        parser.feed(stripped)
        for href, text in parser.entries:
            entry = parse_archive_entry_from_text(href, text)
            if entry:
                entries.append(entry)
    else:
        for line in stripped.splitlines():
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
