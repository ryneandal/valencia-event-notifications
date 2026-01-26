import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import typer

from logger import configure_logging, get_logger
from mailer import build_html, send_email
from models import Event
from normalize import normalize_raw
from storage import EventStorage

app = typer.Typer(help="Valencia Events digest workflow manager.")

logger = get_logger(__name__)


def run_scrapers() -> list[dict]:
    """Run all configured scrapers and collect raw events.

    Returns:
        List of raw event dictionaries from all scrapers
    """
    output_file = Path("output/events.jsonl")
    output_file.parent.mkdir(exist_ok=True)

    # Run Visit Valencia spider
    logger.info("Running Visit Valencia spider...")
    try:
        subprocess.run(
            [
                "scrapy",
                "crawl",
                "visit_valencia",
                "-O",  # Overwrite
                str(output_file),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"Scraper failed: {e.stderr}")

    raw_events = []
    if output_file.exists():
        with open(output_file, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        raw_events.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("Skipping invalid JSON line")

    return raw_events


def filter_events_for_tomorrow(events: list[Event]) -> list[Event]:
    """Filter events to only those happening tomorrow.

    Args:
        events: List of all events

    Returns:
        List of events scheduled for tomorrow
    """
    # Use local time for tomorrow logic
    import pytz

    tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(tz)
    tomorrow = (now + timedelta(days=1)).date()

    return [event for event in events if event.start.date() == tomorrow]


@app.command()
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
    app()
