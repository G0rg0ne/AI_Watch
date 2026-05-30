"""Tests for archive parsing."""

from datetime import datetime

from backend.app.services.alphasignal.archive_parser import (
    build_dedup_key,
    parse_archive_entries,
    parse_archive_entry_from_text,
    split_title_and_date,
)


SAMPLE_ARCHIVE_HTML = """
<div class="space-y-3">
  <a href="/newsletter/solo-bot-ceiling">
    <div class="rounded p-2 hover:bg-gray-50/5 transition-colors">
      🤖 The solo bot ceiling: why enterprises need a team agent 5/29/2026, 7:59:48 PM
    </div>
  </a>
  <a href="/newsletter/older-newsletter">
    <div class="rounded p-2 hover:bg-gray-50/5 transition-colors">
      🧠 Older AI newsletter headline 5/28/2026, 6:00:00 PM
    </div>
  </a>
</div>
"""

SAMPLE_ARCHIVE_API_JSON = """
{
  "metadata": {"total_records": 2, "total_pages": 1, "current_page": 1, "limit": 10},
  "data": [
    {
      "_id": "6a19d414efdf9f012014aead",
      "subject": "🤖 The solo bot ceiling: why enterprises need a team agent",
      "timestamp": "2026-05-29T17:59:48.063Z",
      "as_campaign_id": "976d7dd535070c1c"
    },
    {
      "_id": "6a17cd77442273a576f54e10",
      "subject": "Older AI newsletter headline",
      "timestamp": "2026-05-28T05:07:02.362Z",
      "as_campaign_id": "c04b52394712b3e4"
    }
  ]
}
"""


def test_split_title_and_date() -> None:
    text = "🤖 The solo bot ceiling: why enterprises need a team agent 5/29/2026, 7:59:48 PM"
    title, published_at = split_title_and_date(text)
    assert title == "🤖 The solo bot ceiling: why enterprises need a team agent"
    assert published_at == datetime(2026, 5, 29, 19, 59, 48)


def test_parse_archive_entry_from_text() -> None:
    text = "🤖 The solo bot ceiling: why enterprises need a team agent 5/29/2026, 7:59:48 PM"
    entry = parse_archive_entry_from_text("/newsletter/solo-bot-ceiling", text)
    assert entry is not None
    assert entry.url == "https://alphasignal.ai/newsletter/solo-bot-ceiling"
    assert "solo bot ceiling" in entry.title


def test_parse_archive_entries_sorts_newest_first() -> None:
    entries = parse_archive_entries(SAMPLE_ARCHIVE_HTML)
    assert len(entries) == 2
    assert entries[0].published_at > entries[1].published_at
    assert "solo bot ceiling" in entries[0].title.lower()


def test_parse_archive_api_json_builds_email_urls() -> None:
    entries = parse_archive_entries(SAMPLE_ARCHIVE_API_JSON)
    assert len(entries) == 2
    assert entries[0].url == "https://alphasignal.ai/email/976d7dd535070c1c"
    assert entries[0].published_at > entries[1].published_at
    assert "solo bot ceiling" in entries[0].title.lower()


def test_build_dedup_key_is_stable() -> None:
    published_at = datetime(2026, 5, 29, 19, 59, 48)
    key_a = build_dedup_key("https://alphasignal.ai/a", "Title", published_at)
    key_b = build_dedup_key("https://alphasignal.ai/a", "Title", published_at)
    key_c = build_dedup_key("https://alphasignal.ai/b", "Title", published_at)
    assert key_a == key_b
    assert key_a != key_c
