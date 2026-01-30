import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import typer

from filters import filter_events_for_tomorrow
from logger import configure_logging, get_logger
from mailer import build_html, send_email
from models import Event
from normalize import normalize_raw
from services import run_scrapers
from storage import EventStorage

# Get logger
logger = get_logger(__name__)


def main():
    """Main entry point for the digest workflow.

    Workflow:
    1. Run scrapers to collect raw events
    2. Normalize raw events into Event models
    3. Compute hashes and store in database (deduplicate)
    4. Filter for tomorrow's events
    5. Build HTML email
    6. Send email
    """
    configure_logging()
    logger.info("Starting Valencia Events digest workflow")

    # 1. Run scrapers
    raw_events = run_scrapers()
    logger.info(f"Scraped {len(raw_events)} raw events")

    # 2. Normalize
    events: list[Event] = []
    for raw in raw_events:
        try:
            events.append(normalize_raw(raw))
        except ValueError as e:
            logger.warning(f"Failed to normalize event: {e}")

    # 3. Store (with deduplication)
    storage = EventStorage()
    new_count = 0
    for event in events:
        if storage.store_event(event):
            new_count += 1
    logger.info(f"Stored {new_count} new events")

    # 4. Filter for tomorrow
    tomorrow_events = filter_events_for_tomorrow(events)
    logger.info(f"Found {len(tomorrow_events)} events for tomorrow")

    # 5. Build & Send email
    if tomorrow_events:
        target_date = tomorrow_events[0].start  # approximate date
        html = build_html(tomorrow_events, target_date)

        recipient = os.environ.get("RECIPIENT_EMAIL")
        if recipient:
            logger.info(f"Sending email to {recipient}")
            sent = send_email(
                subject=f"Valencia Events - {target_date.strftime('%d %b')}",
                html_body=html,
                to_email=recipient,
            )
            if sent:
                logger.info("Email sent successfully")
            else:
                logger.error("Failed to send email")
        else:
            logger.warning("No RECIPIENT_EMAIL configured, skipping email")
    else:
        logger.info("No events for tomorrow, skipping email")

    storage.close()


if __name__ == "__main__":
    typer.run(main)
