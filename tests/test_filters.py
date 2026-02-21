"""Tests for filtering and ranking logic."""

from datetime import datetime, timedelta

import pytz

from valencia_events.filters import rank_and_limit_events
from valencia_events.models import Event

TZ = pytz.timezone("Europe/Madrid")


def _event(title: str, start: datetime, source: str = "test") -> Event:
    return Event(
        title=title,
        start=start,
        url=f"https://example.com/{title.lower()}",
        description="",
        source=source,
    )


def test_rank_and_limit_events_caps_at_20_and_orders_by_time():
    base = TZ.localize(datetime(2025, 10, 12, 9, 0))
    events = [
        _event(f"Event {idx}", base + timedelta(minutes=idx), source="source_b")
        for idx in range(25)
    ]

    selected = rank_and_limit_events(list(reversed(events)), limit=20)

    assert len(selected) == 20
    assert selected[0].title == "Event 0"
    assert selected[-1].title == "Event 19"
