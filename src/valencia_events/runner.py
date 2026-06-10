"""Digest runner helpers."""

from __future__ import annotations

from .filters import filter_events_for_tomorrow
from .logger import get_logger
from .mailer import build_html, send_email
from .models import Event, User
from .normalize import normalize_raw
from .personalization import (
    GeminiEventRanker,
    build_profile_from_preferences_blob,
    rank_events_for_family,
)
from .storage import EventStorage

logger = get_logger(__name__)


def normalize_and_store_events(
    *,
    raw_events: list[dict],
    storage: EventStorage,
) -> list[Event]:
    """Normalize raw events and persist only newly inserted events.

    Args:
        raw_events: Raw scraped event dictionaries.
        storage: Storage backend used for deduplication and persistence.

    Returns:
        Normalized events that were inserted into storage.
    """
    deduped_events: list[Event] = []
    for raw in raw_events:
        try:
            event = normalize_raw(raw)
        except ValueError as exc:
            logger.warning(f"Failed to normalize event: {exc}")
            continue

        if storage.store_event(event):
            deduped_events.append(event)

    return deduped_events


def select_tomorrow_events(events: list[Event]) -> list[Event]:
    """Return only events occurring tomorrow.

    Args:
        events: Candidate events.

    Returns:
        Events that fall on tomorrow's local date.
    """
    return filter_events_for_tomorrow(events)


def fire_digest_for_user(
    *,
    user: User,
    events: list[Event],
    max_email_events: int = 20,
    ranker: GeminiEventRanker | None = None,
) -> bool:
    """Build and send a digest for one specific user.

    Args:
        user: Target user.
        events: Candidate events to rank and email.
        max_email_events: Maximum number of events to include.
        ranker: Optional custom ranker implementation.

    Returns:
        True when an email was sent successfully, otherwise False.
    """
    if not user.is_active:
        logger.info(f"Skipping inactive user: {user.email}")
        return False

    if not events:
        logger.info(f"No events available for user {user.email}")
        return False

    family_profile = build_profile_from_preferences_blob(user.preferences)
    selection = rank_events_for_family(
        events,
        limit=max_email_events,
        ranker=ranker,
        family_profile=family_profile,
    )

    digest_events = selection.events
    if not digest_events:
        logger.info(f"No ranked digest events for user {user.email}")
        return False

    target_date = digest_events[0].start
    html = build_html(
        digest_events,
        target_date,
        personalization_summary=selection.summary,
        event_feedback=selection.feedback_by_hash,
    )
    return send_email(
        subject=f"Valencia Events - {target_date.strftime('%d %b')}",
        html_body=html,
        to_email=user.email,
    )
