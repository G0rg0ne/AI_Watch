"""Parse newsletter pages into highlight and detailed news items."""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

from shared.schemas.alphasignal import ArchiveEntry, NewsItem, NewsletterDigest

logger = logging.getLogger(__name__)

NEWSLETTER_BASE_URL = "https://alphasignal.ai"
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")


class _NewsletterHTMLParser(HTMLParser):
    """Extract headings, paragraphs, and links from newsletter HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[dict[str, str | None]] = []
        self._current_tag: str | None = None
        self._current_text: list[str] = []
        self._current_links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        if tag_lower in {"h1", "h2", "h3", "h4", "p", "li"}:
            self._flush_block()
            self._current_tag = tag_lower
            self._current_text = []
            self._current_links = []
        if tag_lower == "a":
            href = dict(attrs).get("href")
            if href:
                self._current_links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"h1", "h2", "h3", "h4", "p", "li"}:
            self._flush_block()

    def handle_data(self, data: str) -> None:
        if self._current_tag:
            self._current_text.append(data)

    def _flush_block(self) -> None:
        if not self._current_tag:
            return
        text = " ".join(part.strip() for part in self._current_text if part.strip()).strip()
        if text:
            self.blocks.append(
                {
                    "tag": self._current_tag,
                    "text": text,
                    "link": self._current_links[0] if self._current_links else None,
                }
            )
        self._current_tag = None
        self._current_text = []
        self._current_links = []

    def close(self) -> None:
        self._flush_block()
        super().close()


def _normalize_detail_url(link: str | None) -> str | None:
    if not link:
        return None
    if link.startswith("http"):
        return link
    return urljoin(NEWSLETTER_BASE_URL, link)


def _is_heading(tag: str | None) -> bool:
    return tag in {"h1", "h2", "h3", "h4"} if tag else False


def parse_newsletter_from_blocks(
    archive_entry: ArchiveEntry,
    blocks: list[dict[str, str | None]],
) -> NewsletterDigest:
    """Convert parsed HTML blocks into structured newsletter content."""
    highlights: list[NewsItem] = []
    detailed_items: list[NewsItem] = []
    section = "highlights"
    pending_title: str | None = None

    for block in blocks:
        tag = block.get("tag")
        text = (block.get("text") or "").strip()
        link = _normalize_detail_url(block.get("link"))
        if not text:
            continue

        lowered = text.lower()
        if "in today's signal" in lowered or lowered.startswith("highlights"):
            section = "highlights"
            continue
        if lowered.startswith("the rest of today's signal") or lowered.startswith("detailed"):
            section = "detailed"
            continue

        if _is_heading(tag):
            item = NewsItem(
                title=text,
                summary=None,
                detail_url=link,
                section="highlight" if section == "highlights" else "detailed",
            )
            if section == "highlights":
                highlights.append(item)
            else:
                detailed_items.append(item)
            pending_title = text
            continue

        if pending_title and section == "detailed":
            for item in reversed(detailed_items):
                if item.title == pending_title and not item.summary:
                    item.summary = text
                    if link and not item.detail_url:
                        item.detail_url = link
                    break
            pending_title = None
            continue

        if section == "highlights":
            highlights.append(
                NewsItem(title=text, summary=None, detail_url=link, section="highlight")
            )
        else:
            detailed_items.append(
                NewsItem(title=text, summary=text, detail_url=link, section="detailed")
            )

    return NewsletterDigest(
        archive_entry=archive_entry,
        highlights=highlights,
        detailed_items=detailed_items,
    )


def parse_newsletter_plaintext(archive_entry: ArchiveEntry, content: str) -> NewsletterDigest:
    """Parse newsletter content from plain text/markdown-like Tavily output."""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    highlights: list[NewsItem] = []
    detailed_items: list[NewsItem] = []
    section = "highlights"
    pending_title: str | None = None
    pending_summary_lines: list[str] = []

    def flush_detailed_item() -> None:
        nonlocal pending_title, pending_summary_lines
        if not pending_title:
            return
        summary = " ".join(pending_summary_lines).strip() or None
        link_match = URL_PATTERN.search(" ".join(pending_summary_lines))
        detail_url = link_match.group(0) if link_match else None
        detailed_items.append(
            NewsItem(
                title=pending_title,
                summary=summary,
                detail_url=detail_url,
                section="detailed",
            )
        )
        pending_title = None
        pending_summary_lines = []

    for line in lines:
        lowered = line.lower()
        if "in today's signal" in lowered:
            section = "highlights"
            continue
        if "the rest of today's signal" in lowered or lowered.startswith("detailed"):
            flush_detailed_item()
            section = "detailed"
            continue

        if line.startswith("#"):
            flush_detailed_item()
            title = line.lstrip("#").strip()
            if section == "highlights":
                highlights.append(
                    NewsItem(title=title, summary=None, detail_url=None, section="highlight")
                )
            else:
                pending_title = title
            continue

        if section == "highlights":
            link_match = URL_PATTERN.search(line)
            highlights.append(
                NewsItem(
                    title=line,
                    summary=None,
                    detail_url=link_match.group(0) if link_match else None,
                    section="highlight",
                )
            )
            continue

        if pending_title is None:
            pending_title = line
            continue

        if URL_PATTERN.fullmatch(line) or line.lower().startswith("read more"):
            pending_summary_lines.append(line)
            flush_detailed_item()
            continue

        pending_summary_lines.append(line)

    flush_detailed_item()
    return NewsletterDigest(
        archive_entry=archive_entry,
        highlights=highlights,
        detailed_items=detailed_items,
    )


def parse_newsletter(archive_entry: ArchiveEntry, content: str) -> NewsletterDigest:
    """Parse a newsletter page from HTML or plain text."""
    if "<" in content and ">" in content:
        parser = _NewsletterHTMLParser()
        parser.feed(content)
        parser.close()
        digest = parse_newsletter_from_blocks(archive_entry, parser.blocks)
        if digest.highlights or digest.detailed_items:
            logger.info(
                "Parsed newsletter HTML: %d highlights, %d detailed items",
                len(digest.highlights),
                len(digest.detailed_items),
            )
            return digest

    digest = parse_newsletter_plaintext(archive_entry, content)
    logger.info(
        "Parsed newsletter text: %d highlights, %d detailed items",
        len(digest.highlights),
        len(digest.detailed_items),
    )
    return digest
