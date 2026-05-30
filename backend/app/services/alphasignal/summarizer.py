"""OpenAI summarization for AlphaSignal newsletter digests."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langsmith import Client
from langsmith.wrappers import wrap_openai
from openai import OpenAI

from backend.app.core.config import Settings, get_settings
from backend.app.services.tracing import traceable_step
from shared.schemas.alphasignal import NewsletterDigest

logger = logging.getLogger(__name__)


def _message_content_to_str(content: Any) -> str:
    """Normalize LangChain message content to a plain string for OpenAI."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(parts)
    return str(content)


def _langchain_messages_to_openai(messages: list[BaseMessage]) -> list[dict[str, str]]:
    """Convert LangChain chat messages to OpenAI chat completion message dicts."""
    openai_messages: list[dict[str, str]] = []
    for message in messages:
        if isinstance(message, SystemMessage):
            role = "system"
        elif isinstance(message, HumanMessage):
            role = "user"
        elif isinstance(message, AIMessage):
            role = "assistant"
        else:
            msg_type = getattr(message, "type", "human")
            role = "assistant" if msg_type == "ai" else "system" if msg_type == "system" else "user"
        openai_messages.append(
            {"role": role, "content": _message_content_to_str(message.content)}
        )
    return openai_messages


class NewsletterSummarizer:
    """Generate email-ready summaries using OpenAI and LangSmith-managed prompts."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = wrap_openai(OpenAI(api_key=self.settings.openai_api_key))
        client_kwargs: dict[str, str] = {}
        if self.settings.langchain_api_key:
            client_kwargs["api_key"] = self.settings.langchain_api_key
        self._langsmith_client = Client(**client_kwargs)
        self._prompt_template: ChatPromptTemplate | None = None

    def _build_newsletter_payload(self, digest: NewsletterDigest) -> str:
        payload = {
            "newsletter_title": digest.archive_entry.title,
            "published_at": digest.archive_entry.published_at.isoformat(),
            "newsletter_url": digest.archive_entry.url,
            "highlights": [item.model_dump() for item in digest.highlights],
            "detailed_items": [item.model_dump() for item in digest.detailed_items],
        }
        return json.dumps(payload, indent=2)

    def _get_prompt_template(self) -> ChatPromptTemplate:
        """Pull and cache the summarizer prompt from LangSmith."""
        if self._prompt_template is None:
            prompt_id = self.settings.langsmith_summarizer_prompt
            logger.info("Pulling summarizer prompt from LangSmith: %s", prompt_id)
            pulled = self._langsmith_client.pull_prompt(prompt_id)
            if not isinstance(pulled, ChatPromptTemplate):
                raise RuntimeError(
                    f"LangSmith prompt '{prompt_id}' must be a ChatPromptTemplate, "
                    f"got {type(pulled).__name__}"
                )
            self._prompt_template = pulled
        return self._prompt_template

    def _build_openai_messages(self, digest: NewsletterDigest) -> list[dict[str, str]]:
        template = self._get_prompt_template()
        newsletter_payload = self._build_newsletter_payload(digest)
        lc_messages = template.format_messages(newsletter_payload=newsletter_payload)
        return _langchain_messages_to_openai(lc_messages)

    @traceable_step("openai_summarize_newsletter")
    def summarize(self, digest: NewsletterDigest) -> str:
        """Return a formatted email body summarizing the newsletter."""
        logger.info("Summarizing newsletter with OpenAI model %s", self.settings.openai_model)
        messages = self._build_openai_messages(digest)
        response = self.client.chat.completions.create(
            model=self.settings.openai_model,
            messages=messages,
            temperature=0.3,
        )
        content = response.choices[0].message.content or ""
        if not content.strip():
            raise RuntimeError("OpenAI returned an empty summary")
        return content.strip()

    def build_email_subject(self, digest: NewsletterDigest) -> str:
        """Build a concise email subject line."""
        return f"AlphaSignal Digest: {digest.archive_entry.title}"
