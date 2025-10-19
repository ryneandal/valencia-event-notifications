"""Main orchestrator for the Valencia Events digest workflow.

Coordinates scraping, normalization, storage, and email sending.
"""

import logging
from datetime import datetime, timedelta

from models import Event

logger = logging.getLogger(__name__)


def run_scrapers() -> list[dict]:
    """Run all configured scrapers and collect raw events.

    Returns:
        List of raw event dictionaries from all scrapers
    """
    # TODO: Implement scraper execution
    # Should:
    # - Run Scrapy spiders
    # - Collect output JSONL files
    # - Return combined list of raw items
    raise NotImplementedError("run_scrapers() not yet implemented")


def filter_events_for_tomorrow(events: list[Event]) -> list[Event]:
    """Filter events to only those happening tomorrow.

    Args:
        events: List of all events

    Returns:
        List of events scheduled for tomorrow
    """
    tomorrow = datetime.now().date() + timedelta(days=1)
    return [event for event in events if event.start.date() == tomorrow]


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
    logger.info("Starting Valencia Events digest workflow")

    # TODO: Implement complete workflow
    # 1. Run scrapers
    # raw_events = run_scrapers()

    # 2. Normalize
    # events = [normalize_raw(raw) for raw in raw_events]

    # 3. Store (with deduplication)
    # storage = EventStorage()
    # for event in events:
    #     event.event_hash = compute_event_hash(event)
    #     storage.store_event(event)

    # 4. Filter for tomorrow
    # tomorrow_events = filter_events_for_tomorrow(events)

    # 5. Build email
    # html = build_html(tomorrow_events, datetime.now() + timedelta(days=1))

    # 6. Send email
    # send_email(
    #     subject="València Events - Tomorrow",
    #     html_body=html,
    #     to_email=os.environ.get("RECIPIENT_EMAIL")
    # )

    raise NotImplementedError("main() workflow not yet implemented")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
