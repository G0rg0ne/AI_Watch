"""Tests for newsletter parsing."""

from datetime import datetime

from backend.app.services.alphasignal.newsletter_parser import parse_newsletter
from shared.schemas.alphasignal import ArchiveEntry


def _entry() -> ArchiveEntry:
    return ArchiveEntry(
        title="🤖 Sample Newsletter",
        url="https://alphasignal.ai/newsletter/sample",
        published_at=datetime(2026, 5, 29, 19, 59, 48),
    )


SAMPLE_NEWSLETTER_TEXT = """
# In Today's Signal
OpenAI launches new model
Anthropic releases Claude update

# The Rest of Today's Signal
## Google DeepMind breakthrough
Researchers achieved a major benchmark improvement in reasoning tasks.
https://example.com/deepmind-story

## Meta open-sources new framework
Meta released a lightweight training framework for edge deployment.
Read more: https://example.com/meta-framework
"""


def test_parse_newsletter_plaintext_sections() -> None:
    digest = parse_newsletter(_entry(), SAMPLE_NEWSLETTER_TEXT)
    assert len(digest.highlights) >= 2
    assert len(digest.detailed_items) >= 2
    assert any("DeepMind" in item.title for item in digest.detailed_items)
    assert any(item.detail_url for item in digest.detailed_items)


SAMPLE_NEWSLETTER_HTML = """
<html>
<body>
<h2>In Today's Signal</h2>
<h3>OpenAI launches new model</h3>
<h3>Anthropic releases Claude update</h3>
<h2>The Rest of Today's Signal</h2>
<h3>Google DeepMind breakthrough</h3>
<p>Researchers achieved a major benchmark improvement in reasoning tasks.</p>
<a href="https://example.com/deepmind-story">Read more</a>
</body>
</html>
"""


def test_parse_newsletter_html() -> None:
    digest = parse_newsletter(_entry(), SAMPLE_NEWSLETTER_HTML)
    assert digest.highlights
    assert digest.detailed_items
    detailed = digest.detailed_items[0]
    assert "DeepMind" in detailed.title
    assert detailed.summary is not None
