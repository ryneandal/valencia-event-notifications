"""Email digest generation and sending."""

import logging
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .models import Event

logger = logging.getLogger(__name__)


def generate_html_digest(events: list[Event], date: datetime) -> str:
    """Generate HTML email digest for events.

    Args:
        events: List of events to include in digest
        date: Date for the events

    Returns:
        HTML string for email body
    """
    if not events:
        return f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #333; }}
                p {{ color: #666; }}
            </style>
        </head>
        <body>
            <h1>No Events Tomorrow</h1>
            <p>There are no events scheduled for {date.strftime('%B %d, %Y')} in downtown València.</p>
        </body>
        </html>
        """

    # Sort events by start time
    sorted_events = sorted(events, key=lambda e: e.start_time)

    event_html = ""
    for event in sorted_events:
        neighborhood_str = f" ({event.neighborhood})" if event.neighborhood else ""
        time_str = event.start_time.strftime("%I:%M %p")

        event_html += f"""
        <div style="margin-bottom: 20px; padding: 15px; border-left: 4px solid #4CAF50; background-color: #f9f9f9;">
            <h3 style="margin-top: 0; color: #2c3e50;">{event.title}</h3>
            <p style="margin: 5px 0;"><strong>Time:</strong> {time_str}</p>
            <p style="margin: 5px 0;"><strong>Location:</strong> {event.location or 'TBD'}{neighborhood_str}</p>
            {f'<p style="margin: 5px 0;">{event.description}</p>' if event.description else ''}
            {f'<p style="margin: 5px 0;"><a href="{event.url}" style="color: #4CAF50;">More Info</a></p>' if event.url else ''}
            <p style="margin: 5px 0; font-size: 12px; color: #999;">Source: {event.source}</p>
        </div>
        """

    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #fff; }}
            h1 {{ color: #2c3e50; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }}
            h3 {{ color: #2c3e50; }}
            a {{ text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <h1>Valencia Events - {date.strftime('%B %d, %Y')}</h1>
        <p style="color: #666; margin-bottom: 30px;">
            Found {len(events)} event{'s' if len(events) != 1 else ''} in downtown València for tomorrow.
        </p>
        {event_html}
        <hr style="margin-top: 30px; border: none; border-top: 1px solid #ddd;">
        <p style="color: #999; font-size: 12px;">
            This is an automated email from Valencia Event Notifications.
        </p>
    </body>
    </html>
    """

    return html


def send_email_digest(
    events: list[Event],
    date: datetime,
    recipient_email: str,
    sender_email: str = None,
    sender_password: str = None,
) -> bool:
    """Send email digest of events.

    Args:
        events: List of events to include
        date: Date for the events
        recipient_email: Email address to send to
        sender_email: Gmail address to send from (defaults to env var GMAIL_USER)
        sender_password: Gmail app password (defaults to env var GMAIL_PASSWORD)

    Returns:
        True if email sent successfully, False otherwise
    """
    sender_email = sender_email or os.environ.get("GMAIL_USER")
    sender_password = sender_password or os.environ.get("GMAIL_PASSWORD")

    if not sender_email or not sender_password:
        logger.error("Gmail credentials not provided")
        return False

    # Create message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"València Events - {date.strftime('%B %d, %Y')}"
    msg["From"] = sender_email
    msg["To"] = recipient_email

    # Generate HTML content
    html_content = generate_html_digest(events, date)
    html_part = MIMEText(html_content, "html")
    msg.attach(html_part)

    # Send email via Gmail SMTP
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())

        logger.info(f"Email digest sent successfully to {recipient_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False
