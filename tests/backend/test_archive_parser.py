"""Tests for archive parsing."""

from datetime import datetime

from backend.app.services.alphasignal.archive_parser import (
    build_dedup_key,
    build_news_article_slug,
    build_news_article_url,
    extract_article_html_from_page,
    parse_archive_entries,
)

SAMPLE_OFFICIAL_NEWS_API_JSON = """
{
  "metadata": {"total_records": 2, "total_pages": 1, "current_page": 1, "limit": 10},
  "data": [
    {
      "news_id": "eb246d3a-921a-4a55-9e5b-dd318647604d",
      "title": "Anthropic's Claude Beats ChemDraw at Reading Molecular Spectra Without Chemistry Training",
      "publish_time": "2026-06-05T19:27:21.000Z"
    },
    {
      "news_id": "a6913e64-22c0-4f7a-a249-d3b18c8beb85",
      "title": "OpenAI's Codex Gains a Personal Dashboard Tracking Your Token Usage",
      "publish_time": "2026-06-04T23:16:03.000Z"
    }
  ]
}
"""

SAMPLE_ARTICLE_PAGE_HTML = (
    '<script>"articleDetails":{"html_text":"\\u003cp\\u003eArticle body\\u003c/p\\u003e",'
    '"summary_html":"\\u003cul\\u003e\\u003cli\\u003eTakeaway one\\u003c/li\\u003e\\u003c/ul\\u003e"}'
    "</script>"
)


def test_parse_official_news_api_json_builds_news_urls() -> None:
    entries = parse_archive_entries(SAMPLE_OFFICIAL_NEWS_API_JSON)
    assert len(entries) == 2
    assert entries[0].url.startswith("https://alphasignal.ai/news/")
    assert entries[0].published_at > entries[1].published_at
    assert "Anthropic's Claude" in entries[0].title


def test_parse_archive_entries_returns_empty_for_non_json() -> None:
    assert parse_archive_entries("<html></html>") == []


def test_build_dedup_key_is_stable() -> None:
    published_at = datetime(2026, 5, 29, 19, 59, 48)
    key_a = build_dedup_key("https://alphasignal.ai/a", "Title", published_at)
    key_b = build_dedup_key("https://alphasignal.ai/a", "Title", published_at)
    key_c = build_dedup_key("https://alphasignal.ai/b", "Title", published_at)
    assert key_a == key_b
    assert key_a != key_c


def test_build_news_article_slug_truncates_to_70_chars() -> None:
    title = (
        "Anthropic's Claude Beats ChemDraw at Reading Molecular Spectra "
        "Without Chemistry Training"
    )
    slug = build_news_article_slug(title)
    assert len(slug) == 70
    assert slug == "anthropic-s-claude-beats-chemdraw-at-reading-molecular-spectra-without"


def test_build_news_article_url_uses_official_news_path() -> None:
    url = build_news_article_url("OpenAI's Codex Gains a Personal Dashboard")
    assert url == (
        "https://alphasignal.ai/news/openai-s-codex-gains-a-personal-dashboard"
    )


def test_extract_article_html_from_page_decodes_nextjs_payload() -> None:
    html = extract_article_html_from_page(SAMPLE_ARTICLE_PAGE_HTML)
    assert html is not None
    assert "<li>Takeaway one</li>" in html
    assert "<p>Article body</p>" in html
