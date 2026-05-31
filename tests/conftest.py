"""Pytest configuration."""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Minimal env defaults so Settings validation succeeds during tests.
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("SMTP_HOST", "smtp.test.local")
os.environ.setdefault("SMTP_USER", "test-user")
os.environ.setdefault("SMTP_PASSWORD", "test-password")
os.environ.setdefault("EMAIL_FROM", "from@test.local")
os.environ.setdefault("EMAIL_TO", "to@test.local")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["ALPHASIGNAL_START_DATE"] = ""


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Ensure tests do not reuse cached Settings loaded from a developer .env file."""
    from backend.app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
