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


def test_build_dedup_key_is_stable() -> None:
    published_at = datetime(2026, 5, 29, 19, 59, 48)
    key_a = build_dedup_key("https://alphasignal.ai/a", "Title", published_at)
    key_b = build_dedup_key("https://alphasignal.ai/a", "Title", published_at)
    key_c = build_dedup_key("https://alphasignal.ai/b", "Title", published_at)
    assert key_a == key_b
    assert key_a != key_c
