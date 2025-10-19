"""Email functionality for sending event digests.

Builds HTML emails and sends them via SMTP.
"""

import os
from datetime import datetime

from models import Event


def build_html(events: list[Event], date: datetime) -> str:
    """Build HTML email body from list of events.

    Args:
        events: List of events to include in digest
        date: Date for the digest (e.g., tomorrow's date)

    Returns:
        HTML string for email body

    Example:
        >>> events = [Event(...), Event(...)]
        >>> html = build_html(events, datetime(2025, 10, 12))
        >>> "<!DOCTYPE html>" in html
        True
    """
    # TODO: Implement HTML email template
    # Should include:
    # - Nice header with date
    # - List of events with title, time, description, link
    # - Footer
    raise NotImplementedError("build_html() not yet implemented")


def send_email(
    subject: str,
    html_body: str,
    to_email: str,
    from_email: str | None = None,
    smtp_user: str | None = None,
    smtp_password: str | None = None,
    smtp_host: str = "smtp.gmail.com",
    smtp_port: int = 587,
) -> bool:
    """Send HTML email via SMTP.

    Credentials should be provided via environment variables:
    - SMTP_USER
    - SMTP_APP_PASSWORD

    Args:
        subject: Email subject line
        html_body: HTML email body
        to_email: Recipient email address
        from_email: Sender email address (defaults to SMTP_USER)
        smtp_user: SMTP username (defaults to env var SMTP_USER)
        smtp_password: SMTP password (defaults to env var SMTP_APP_PASSWORD)
        smtp_host: SMTP server hostname
        smtp_port: SMTP server port

    Returns:
        True if email was sent successfully

    Raises:
        ValueError: If required credentials are missing
    """
    # Get credentials from environment if not provided
    smtp_user = smtp_user or os.environ.get("SMTP_USER")
    smtp_password = smtp_password or os.environ.get("SMTP_APP_PASSWORD")
    from_email = from_email or smtp_user

    if not smtp_user or not smtp_password:
        raise ValueError(
            "SMTP credentials required. Set SMTP_USER and SMTP_APP_PASSWORD "
            "environment variables."
        )

    # TODO: Implement email sending
    # Should:
    # - Create MIME message
    # - Connect to SMTP server with TLS
    # - Authenticate
    # - Send message
    # - Handle errors gracefully
    raise NotImplementedError("send_email() not yet implemented")
