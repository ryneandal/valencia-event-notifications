"""Utilities for filtering events."""

from datetime import datetime, timedelta

import pytz

from .models import Event


def get_tomorrow_madrid() -> datetime:
    """Get tomorrow's date in Europe/Madrid timezone.

    Returns:
        Tomorrow's date at midnight in Madrid timezone
    """
    madrid_tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(madrid_tz)
    tomorrow = now + timedelta(days=1)
    # Set to start of day (midnight)
    return tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)


def filter_events_for_tomorrow(events: list[Event]) -> list[Event]:
    """Filter events to only include those happening tomorrow.

    Args:
        events: List of events to filter

    Returns:
        List of events happening tomorrow in Europe/Madrid timezone
    """
    tomorrow = get_tomorrow_madrid()
    day_after = tomorrow + timedelta(days=1)

    filtered = []
    madrid_tz = pytz.timezone("Europe/Madrid")

    for event in events:
        # Ensure event time is timezone-aware
        event_time = event.start_time
        if event_time.tzinfo is None:
            # Assume naive times are in Madrid timezone
            event_time = madrid_tz.localize(event_time)
        else:
            # Convert to Madrid timezone
            event_time = event_time.astimezone(madrid_tz)

        # Check if event is tomorrow
        if tomorrow <= event_time < day_after:
            filtered.append(event)

    return filtered


def deduplicate_events(events: list[Event]) -> list[Event]:
    """Remove duplicate events from the list.

    Args:
        events: List of events (may contain duplicates)

    Returns:
        List of unique events
    """
    # Use a dict to preserve order while removing duplicates
    seen = {}
    for event in events:
        key = (event.title.lower(), event.start_time, event.location)
        if key not in seen:
            seen[key] = event

    return list(seen.values())
