"""Filtering logic for events."""

from datetime import datetime, timedelta

import pytz

from .models import Event


def filter_events_for_tomorrow(events: list[Event]) -> list[Event]:
    """Filter events to only those happening tomorrow.

    Args:
        events: All candidate events.

    Returns:
        Events scheduled for tomorrow in Europe/Madrid local time.
    """
    # Use local time for tomorrow logic
    tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(tz)
    tomorrow = (now + timedelta(days=1)).date()

    return [event for event in events if event.start.date() == tomorrow]


def rank_and_limit_events(events: list[Event], limit: int = 20) -> list[Event]:
    """Apply deterministic ranking and cap the number of events.

    Args:
        events: Events to rank.
        limit: Maximum number of events to return.

    Returns:
        Events sorted by start time, source, and title, truncated to ``limit``.
    """
    ranked = sorted(
        events,
        key=lambda event: (
            event.start,
            event.source.lower(),
            event.title.lower(),
        ),
    )
    return ranked[:limit]
