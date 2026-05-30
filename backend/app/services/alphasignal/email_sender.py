"""SMTP email delivery for AlphaSignal digests."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from backend.app.core.config import Settings, get_settings
from backend.app.services.tracing import traceable_step

logger = logging.getLogger(__name__)


class SmtpEmailSender:
    """Send summary emails through generic SMTP."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @traceable_step("smtp_send_email")
    def send(self, subject: str, body: str) -> None:
        """Send a plain-text email to the configured recipient."""
        message = MIMEMultipart()
        message["From"] = self.settings.email_from
        message["To"] = self.settings.email_to
        message["Subject"] = subject
        message.attach(MIMEText(body, "plain", "utf-8"))

        logger.info("Sending email to %s with subject: %s", self.settings.email_to, subject)
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port) as server:
            if self.settings.smtp_use_tls:
                server.starttls()
            server.login(self.settings.smtp_user, self.settings.smtp_password)
            server.sendmail(
                self.settings.email_from,
                [self.settings.email_to],
                message.as_string(),
            )
        logger.info("Email sent successfully")
