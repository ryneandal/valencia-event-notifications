import os
from typing import Annotated

import typer
from dotenv import load_dotenv

from .filters import filter_events_for_tomorrow
from .logger import configure_logging, get_logger
from .mailer import build_html, send_email
from .models import Event
from .normalize import normalize_raw
from .personalization import rank_events_for_family
from .runner import fire_digest_for_user
from .services import run_scrapers
from .storage import EventStorage

# Get logger
logger = get_logger(__name__)
MAX_EMAIL_EVENTS = 20


def main(
    user_email: Annotated[
        str | None,
        typer.Option(help="Run digest for a specific registered user email"),
    ] = None,
):
    """Run the full digest workflow.

    Args:
        user_email: Optional registered user email to target a single recipient.

    Returns:
        None
    """
    load_dotenv()
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
    if not tomorrow_events:
        logger.info("No events for tomorrow, skipping email")
        storage.close()
        return

    # 5. Send user-targeted digests when users are available
    target_users = []
    if user_email:
        try:
            user = storage.get_user_by_email(user_email)
        except ValueError:
            logger.error(f"Invalid --user-email value: {user_email}")
            storage.close()
            return
        if user:
            target_users = [user]
        else:
            logger.warning(f"Requested user not found: {user_email}")
            storage.close()
            return
    else:
        target_users = storage.get_active_users()

    if target_users:
        logger.info(f"Sending digest to {len(target_users)} user(s)")
        for user in target_users:
            sent = fire_digest_for_user(
                user=user,
                events=tomorrow_events,
                max_email_events=MAX_EMAIL_EVENTS,
            )
            if sent:
                logger.info(f"Email sent successfully to {user.email}")
            else:
                logger.warning(f"No email sent for user {user.email}")
        storage.close()
        return

    # 6. Fallback single recipient flow when no onboarded users are present
    selection = rank_events_for_family(tomorrow_events, limit=MAX_EMAIL_EVENTS)
    digest_events = selection.events
    logger.info(
        "Prepared digest events",
        extra={
            "selected": len(digest_events),
            "available": len(tomorrow_events),
            "limit": MAX_EMAIL_EVENTS,
            "used_llm": selection.used_llm,
        },
    )
    if selection.summary:
        logger.info(f"Personalization summary: {selection.summary}")
    if not digest_events:
        logger.info("No ranked events available, skipping fallback email")
        storage.close()
        return

    target_date = digest_events[0].start  # date already constrained to tomorrow
    html = build_html(
        digest_events,
        target_date,
        personalization_summary=selection.summary,
        event_feedback=selection.feedback_by_hash,
    )

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

    storage.close()


if __name__ == "__main__":
    typer.run(main)
