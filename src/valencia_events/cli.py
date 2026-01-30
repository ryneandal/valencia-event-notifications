import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import typer

from .filters import filter_events_for_tomorrow
from .logger import configure_logging, get_logger
from .mailer import build_html, send_email
from .models import Event
from .normalize import normalize_raw
from .services import run_scrapers
from .storage import EventStorage

# Get logger
logger = get_logger(__name__)

app = typer.Typer()


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
):
    """Start the user management web server."""
    import uvicorn
    uvicorn.run(
        "valencia_events.web.app:app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command()
def run():
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

    # 5. Filter for tomorrow
    tomorrow_events = filter_events_for_tomorrow(events)
    logger.info(f"Found {len(tomorrow_events)} events for tomorrow")

    # 6. Personalize & Send
    from .filters import LLMFilter
    
    # Initialize LLM (will skip if no key)
    llm_filter = LLMFilter()
    
    # Get active users
    active_users = storage.get_active_users()
    logger.info(f"Found {len(active_users)} active users")

    if tomorrow_events:
        target_date = tomorrow_events[0].start
        
        if active_users:
            for user in active_users:
                email = user["email"]
                preferences = user["preferences"]
                logger.info(f"Processing digest for {email}")
                
                # Filter for user (or use all if no prefs/LLM)
                user_events = llm_filter.filter_for_user(tomorrow_events, preferences)
                
                if user_events:
                    html = build_html(user_events, target_date)
                    sent = send_email(
                        subject=f"Your Valencia Events - {target_date.strftime('%d %b')}",
                        html_body=html,
                        to_email=email,
                    )
                    if sent:
                        logger.info(f"Sent email to {email}")
                    else:
                        logger.error(f"Failed to send to {email}")
                else:
                    logger.info(f"No matching events for {email}")

        # Fallback / Admin copy
        recipient = os.environ.get("RECIPIENT_EMAIL")
        if recipient and not any(u["email"] == recipient for u in active_users):
            logger.info(f"Sending admin copy to {recipient}")
            html = build_html(tomorrow_events, target_date)
            send_email(
                subject=f"Valencia Events (Admin) - {target_date.strftime('%d %b')}",
                html_body=html,
                to_email=recipient,
            )
    else:
        logger.info("No events for tomorrow, skipping email")

    storage.close()


def main():
    """Entry point for script execution."""
    app()

if __name__ == "__main__":
    main()
