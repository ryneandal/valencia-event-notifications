#!/usr/bin/env python3
"""Main runner script for Valencia event notifications."""

import argparse
import logging
import os
import sys

from valencia_events.database import EventDatabase
from valencia_events.email_digest import send_email_digest
from valencia_events.filters import (
    deduplicate_events,
    get_tomorrow_madrid,
)
from valencia_events.scrapers import get_all_scrapers

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for the event notification system."""
    parser = argparse.ArgumentParser(description="Valencia Event Notifications")
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/events.db",
        help="Path to SQLite database file (default: data/events.db)",
    )
    parser.add_argument(
        "--recipient-email",
        type=str,
        help="Email address to send notifications to (defaults to RECIPIENT_EMAIL env var)",
    )
    parser.add_argument(
        "--skip-email", action="store_true", help="Skip sending email (useful for testing)"
    )
    parser.add_argument(
        "--scrape-only", action="store_true", help="Only scrape and store events, do not send email"
    )

    args = parser.parse_args()

    # Initialize database
    logger.info(f"Initializing database at {args.db_path}")
    db = EventDatabase(args.db_path)

    # Scrape events from all sources
    logger.info("Starting event scraping from all sources")
    all_events = []
    scrapers = get_all_scrapers()

    for scraper in scrapers:
        try:
            events = scraper.scrape()
            all_events.extend(events)
            logger.info(f"Scraped {len(events)} events from {scraper.__class__.__name__}")
        except Exception as e:
            logger.error(f"Error scraping from {scraper.__class__.__name__}: {e}")

    # Deduplicate events
    logger.info(f"Total events before deduplication: {len(all_events)}")
    all_events = deduplicate_events(all_events)
    logger.info(f"Total events after deduplication: {len(all_events)}")

    # Store events in database
    added_count = db.add_events(all_events)
    logger.info(f"Added {added_count} new events to database")

    if args.scrape_only:
        logger.info("Scrape-only mode: skipping email")
        return 0

    # Filter for tomorrow's events
    tomorrow = get_tomorrow_madrid()
    tomorrow_events = db.get_events_by_date(tomorrow)
    logger.info(
        f"Found {len(tomorrow_events)} events for tomorrow ({tomorrow.strftime('%Y-%m-%d')})"
    )

    # Send email digest
    if not args.skip_email:
        recipient_email = args.recipient_email or os.environ.get("RECIPIENT_EMAIL")

        if not recipient_email:
            logger.error(
                "No recipient email specified. Use --recipient-email or set RECIPIENT_EMAIL env var"
            )
            return 1

        success = send_email_digest(tomorrow_events, tomorrow, recipient_email)

        if success:
            logger.info("Email digest sent successfully")
            return 0
        else:
            logger.error("Failed to send email digest")
            return 1
    else:
        logger.info("Email sending skipped")
        return 0


if __name__ == "__main__":
    sys.exit(main())
