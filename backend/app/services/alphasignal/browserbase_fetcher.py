"""Fetch AlphaSignal API URLs via Browserbase-hosted Chromium sessions."""

from __future__ import annotations

import logging
from typing import Any

from backend.app.core.config import Settings, get_settings
from backend.app.services.tracing import traceable_step

logger = logging.getLogger(__name__)

_BROWSER_FETCH_JS = """
async (apiUrl) => {
    const response = await fetch(apiUrl, {
        method: "GET",
        credentials: "include",
        headers: {
            Accept: "application/json, text/plain, */*",
        },
    });
    return {
        status: response.status,
        url: response.url,
        text: await response.text(),
    };
}
"""


class BrowserbaseFetchError(RuntimeError):
    """Raised when Browserbase cannot retrieve AlphaSignal content."""


class BrowserbaseFetcher:
    """Retrieve AlphaSignal JSON API responses inside a remote browser session."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _validate_configuration(self) -> None:
        if not self.settings.browserbase_api_key:
            raise BrowserbaseFetchError(
                "BROWSERBASE_API_KEY is required when ALPHASIGNAL_FETCH_MODE is "
                "'browserbase' or when auto mode falls back to Browserbase."
            )

    def _build_session_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "timeout": self.settings.browserbase_session_timeout_seconds,
        }
        if self.settings.browserbase_project_id:
            kwargs["project_id"] = self.settings.browserbase_project_id
        if self.settings.browserbase_region:
            kwargs["region"] = self.settings.browserbase_region
        if self.settings.browserbase_use_proxy:
            kwargs["proxies"] = True
        return kwargs

    @traceable_step("browserbase_fetch_url")
    def fetch_url(self, api_url: str) -> str:
        """Open a Browserbase session and fetch the given AlphaSignal API URL."""
        self._validate_configuration()

        from browserbase import Browserbase
        from playwright.sync_api import sync_playwright

        bb = Browserbase(api_key=self.settings.browserbase_api_key)
        session = bb.sessions.create(**self._build_session_kwargs())
        logger.info(
            "Browserbase session created: id=%s url=%s",
            session.id,
            f"https://browserbase.com/sessions/{session.id}",
        )

        playwright = None
        browser = None
        try:
            playwright = sync_playwright().start()
            browser = playwright.chromium.connect_over_cdp(session.connect_url)
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()

            logger.info(
                "Navigating Browserbase session to AlphaSignal archive: %s",
                self.settings.alphasignal_archive_url,
            )
            page.goto(
                self.settings.alphasignal_archive_url,
                wait_until="domcontentloaded",
                timeout=60_000,
            )

            logger.info("Fetching AlphaSignal API via Browserbase: %s", api_url)
            result = page.evaluate(_BROWSER_FETCH_JS, api_url)
            if not isinstance(result, dict):
                raise BrowserbaseFetchError(
                    f"Unexpected Browserbase fetch result type: {type(result).__name__}"
                )

            status = int(result.get("status") or 0)
            body = str(result.get("text") or "")
            if status == 403:
                raise BrowserbaseFetchError(
                    "AlphaSignal returned 403 Forbidden via Browserbase. "
                    "Try BROWSERBASE_USE_PROXY=true or verify your Browserbase project "
                    "proxy settings."
                )
            if status < 200 or status >= 300:
                raise BrowserbaseFetchError(
                    f"AlphaSignal returned HTTP {status} via Browserbase for {api_url}"
                )

            return body.strip()
        finally:
            if browser is not None:
                browser.close()
            if playwright is not None:
                playwright.stop()
