"""OpenAI summarization for AlphaSignal newsletter digests."""

from __future__ import annotations

import json
import logging

from openai import OpenAI

from backend.app.core.config import Settings, get_settings
from backend.app.services.tracing import traceable_step
from shared.schemas.alphasignal import NewsletterDigest

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an AI/ML news analyst. Summarize AlphaSignal newsletter content clearly and concisely.
Produce:
1. A short executive summary (3-5 sentences)
2. Highlight section with bullet points for top headlines
3. Detailed section with bullet points including each item's resume/summary and its detail link when available
Keep the tone professional and informative. Use plain text suitable for email."""


class NewsletterSummarizer:
    """Generate email-ready summaries using OpenAI."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = OpenAI(api_key=self.settings.openai_api_key)

    def _build_user_prompt(self, digest: NewsletterDigest) -> str:
        payload = {
            "newsletter_title": digest.archive_entry.title,
            "published_at": digest.archive_entry.published_at.isoformat(),
            "newsletter_url": digest.archive_entry.url,
            "highlights": [item.model_dump() for item in digest.highlights],
            "detailed_items": [item.model_dump() for item in digest.detailed_items],
        }
        return (
            "Summarize this AlphaSignal newsletter for email delivery.\n\n"
            f"{json.dumps(payload, indent=2)}"
        )

    @traceable_step("openai_summarize_newsletter")
    def summarize(self, digest: NewsletterDigest) -> str:
        """Return a formatted email body summarizing the newsletter."""
        logger.info("Summarizing newsletter with OpenAI model %s", self.settings.openai_model)
        response = self.client.chat.completions.create(
            model=self.settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": self._build_user_prompt(digest)},
            ],
            temperature=0.3,
        )
        content = response.choices[0].message.content or ""
        if not content.strip():
            raise RuntimeError("OpenAI returned an empty summary")
        return content.strip()

    def build_email_subject(self, digest: NewsletterDigest) -> str:
        """Build a concise email subject line."""
        return f"AlphaSignal Digest: {digest.archive_entry.title}"
