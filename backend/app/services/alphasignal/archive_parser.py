"""Parse AlphaSignal archive page entries."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from urllib.parse import urljoin

from shared.schemas.alphasignal import ArchiveEntry

logger = logging.getLogger(__name__)

ARCHIVE_BASE_URL = "https://alphasignal.ai"
NEWS_ARTICLE_PATH = "/news"
NEWS_SLUG_MAX_LENGTH = 70


def build_dedup_key(url: str, title: str, published_at: datetime) -> str:
    """Build a stable deduplication key for a publication."""
    normalized = f"{url}|{title.strip().lower()}|{published_at.isoformat()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build_news_article_slug(title: str, max_length: int = NEWS_SLUG_MAX_LENGTH) -> str:
    """Build the official AlphaSignal /news/... slug from an article title."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if len(slug) <= max_length:
        return slug
    trimmed = slug[:max_length].rstrip("-")
    return trimmed or slug[:max_length]


def build_news_article_url(title: str, base_url: str = ARCHIVE_BASE_URL) -> str:
    """Build the public AlphaSignal article URL from a title slug."""
    slug = build_news_article_slug(title)
    return urljoin(base_url, f"{NEWS_ARTICLE_PATH}/{slug}")


def is_news_article_url(url: str) -> bool:
    """Return whether a URL points to an official AlphaSignal /news/ article."""
    return "/news/" in url


def extract_news_slug_from_url(url: str) -> str | None:
    """Extract the article slug from an official AlphaSignal /news/... URL."""
    match = re.search(r"/news/([^?#]+)", url)
    if not match:
        return None
    slug = match.group(1).strip("/")
    return slug or None


def parse_api_timestamp(raw_timestamp: str) -> datetime:
    """Parse ISO timestamps returned by the AlphaSignal news API."""
    normalized = raw_timestamp.replace("Z", "+00:00")
    published_at = datetime.fromisoformat(normalized)
    if published_at.tzinfo is not None:
        published_at = published_at.replace(tzinfo=None)
    return published_at


def sanitize_json_payload(content: str) -> str:
    """Undo markdown-style escaping (e.g. `\\_`) that can break JSON parsing."""
    if not content.strip().startswith("{"):
        return content
    return content.replace("\\_", "_")


def extract_api_items(payload: dict) -> list[dict]:
    """Extract news rows from official AlphaSignal API payloads."""
    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        nested = data.get("data")
        if isinstance(nested, list):
            return nested
    return []


def _parse_official_news_item(item: dict, base_url: str) -> ArchiveEntry | None:
    """Parse one official AlphaSignal news API row."""
    title = item.get("title")
    publish_time = item.get("publish_time")
    if not title or not publish_time:
        return None
    try:
        published_at = parse_api_timestamp(str(publish_time))
    except ValueError as exc:
        logger.debug("Skipping official news API row: %s", exc)
        return None
    cleaned_title = str(title).strip()
    return ArchiveEntry(
        title=cleaned_title,
        url=build_news_article_url(cleaned_title, base_url),
        published_at=published_at,
        raw_text=cleaned_title,
    )


def parse_archive_api_json(
    content: str,
    base_url: str = ARCHIVE_BASE_URL,
) -> list[ArchiveEntry]:
    """Parse archive entries from official AlphaSignal news API JSON responses."""
    payload = json.loads(sanitize_json_payload(content))
    items = extract_api_items(payload)
    entries: list[ArchiveEntry] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        entry = _parse_official_news_item(item, base_url)
        if entry is not None:
            entries.append(entry)

    sorted_entries = sorted(entries, key=lambda item: item.published_at, reverse=True)
    logger.info("Parsed %d archive entries from API JSON", len(sorted_entries))
    return sorted_entries


def _decode_nextjs_embedded_string(raw: str) -> str:
    """Decode a JSON string fragment embedded in Next.js flight payloads."""
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        return raw.replace("\\n", "\n").replace('\\"', '"').replace("\\/", "/")


def extract_article_html_from_detail_api(payload: dict) -> str | None:
    """Extract article HTML from the official news detail API JSON response."""
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    details = data.get("articleDetails")
    if not isinstance(details, dict):
        return None
    parts: list[str] = []
    summary = details.get("summary_html")
    body = details.get("html_text")
    if isinstance(summary, str) and summary.strip():
        parts.append(summary.strip())
    if isinstance(body, str) and body.strip():
        parts.append(body.strip())
    if not parts:
        return None
    return "\n".join(parts)


def extract_article_html_from_page(content: str) -> str | None:
    """
    Extract AlphaSignal article HTML from a rendered /news/... page.

    Prefers serialized articleDetails html_text and summary_html from the
    Next.js payload; returns None when neither field is present.
    """
    html_text_match = re.search(r'"html_text":"((?:\\.|[^"\\])*)"', content)
    summary_html_match = re.search(r'"summary_html":"((?:\\.|[^"\\])*)"', content)
    parts: list[str] = []
    if summary_html_match:
        summary = _decode_nextjs_embedded_string(summary_html_match.group(1)).strip()
        if summary:
            parts.append(summary)
    if html_text_match:
        body = _decode_nextjs_embedded_string(html_text_match.group(1)).strip()
        if body:
            parts.append(body)
    if not parts:
        return None
    return "\n".join(parts)


def parse_archive_entries(content: str, base_url: str = ARCHIVE_BASE_URL) -> list[ArchiveEntry]:
    """Parse archive entries from official AlphaSignal news API JSON."""
    stripped = content.strip()
    if not stripped.startswith("{"):
        logger.warning("Expected JSON archive listing from AlphaSignal news API")
        return []

    try:
        return parse_archive_api_json(stripped, base_url=base_url)
    except json.JSONDecodeError:
        logger.warning("Could not parse AlphaSignal news API JSON")
        return []
