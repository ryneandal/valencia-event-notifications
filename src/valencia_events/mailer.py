"""Email functionality for sending event digests.

Builds HTML emails and sends them via SMTP.
"""

import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .models import Event


def build_html(events: list[Event], date: datetime) -> str:
    """Build HTML email body from list of events.

    Args:
        events: List of events to include in digest
        date: Date for the digest (e.g., tomorrow's date)

    Returns:
        HTML string for email body
    """
    date_str = date.strftime("%A, %d %B %Y")

    templates_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(templates_dir))
    template = env.get_template("digest.html")

    return template.render(events=events, date_str=date_str)


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
    smtp_user = smtp_user or os.environ.get("SMTP_USER")
    smtp_password = smtp_password or os.environ.get("SMTP_APP_PASSWORD")
    from_email = from_email or smtp_user

    if not smtp_user or not smtp_password:
        raise ValueError(
            "SMTP credentials required. Set SMTP_USER and SMTP_APP_PASSWORD "
            "environment variables."
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return True
    except smtplib.SMTPException as e:
        print(f"SMTP Error: {e}")
        return False
    except Exception as e:
        print(f"General Email Error: {e}")
        raise
