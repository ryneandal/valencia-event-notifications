"""Tests for event filtering."""

from datetime import datetime, timedelta

import pytz

from valencia_events.filters import (
    deduplicate_events,
    filter_events_for_tomorrow,
    get_tomorrow_madrid,
)
from valencia_events.models import Event


def test_get_tomorrow_madrid():
    """Test getting tomorrow's date in Madrid timezone."""
    tomorrow = get_tomorrow_madrid()

    # Should be tomorrow
    madrid_tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(madrid_tz)
    expected_tomorrow = now + timedelta(days=1)

    assert tomorrow.date() == expected_tomorrow.date()
    # Should be at midnight
    assert tomorrow.hour == 0
    assert tomorrow.minute == 0
    assert tomorrow.second == 0


def test_filter_events_for_tomorrow():
    """Test filtering events for tomorrow."""
    pytz.timezone("Europe/Madrid")
    tomorrow = get_tomorrow_madrid()
    today = tomorrow - timedelta(days=1)
    day_after = tomorrow + timedelta(days=1)

    events = [
        Event(title="Today's Event", start_time=today.replace(hour=18), source="Test"),
        Event(title="Tomorrow's Event 1", start_time=tomorrow.replace(hour=10), source="Test"),
        Event(title="Tomorrow's Event 2", start_time=tomorrow.replace(hour=18), source="Test"),
        Event(title="Day After Event", start_time=day_after.replace(hour=10), source="Test"),
    ]

    filtered = filter_events_for_tomorrow(events)

    assert len(filtered) == 2
    assert all("Tomorrow" in e.title for e in filtered)


def test_filter_events_naive_datetime():
    """Test filtering events with naive datetime (no timezone)."""
    tomorrow = get_tomorrow_madrid()

    # Create event with naive datetime
    event = Event(
        title="Naive Event",
        start_time=datetime(tomorrow.year, tomorrow.month, tomorrow.day, 18, 0),
        source="Test",
    )

    filtered = filter_events_for_tomorrow([event])

    # Should still work, assuming naive times are in Madrid timezone
    assert len(filtered) == 1


def test_deduplicate_events():
    """Test deduplicating events."""
    events = [
        Event(
            title="Event 1",
            start_time=datetime(2024, 1, 15, 18, 0),
            location="Location A",
            source="Source 1",
        ),
        Event(
            title="Event 1",  # Duplicate
            start_time=datetime(2024, 1, 15, 18, 0),
            location="Location A",
            source="Source 2",
        ),
        Event(
            title="Event 2",
            start_time=datetime(2024, 1, 15, 19, 0),
            location="Location B",
            source="Source 1",
        ),
    ]

    deduplicated = deduplicate_events(events)

    assert len(deduplicated) == 2
    assert deduplicated[0].title == "Event 1"
    assert deduplicated[1].title == "Event 2"


def test_deduplicate_case_insensitive():
    """Test that deduplication is case-insensitive for titles."""
    events = [
        Event(
            title="Test Event",
            start_time=datetime(2024, 1, 15, 18, 0),
            location="Location A",
            source="Source 1",
        ),
        Event(
            title="test event",  # Same title, different case
            start_time=datetime(2024, 1, 15, 18, 0),
            location="Location A",
            source="Source 2",
        ),
    ]

    deduplicated = deduplicate_events(events)

    assert len(deduplicated) == 1


def test_deduplicate_preserves_order():
    """Test that deduplication preserves the order of first occurrence."""
    events = [
        Event(title="Event C", start_time=datetime(2024, 1, 15, 20, 0), source="Test"),
        Event(title="Event A", start_time=datetime(2024, 1, 15, 18, 0), source="Test"),
        Event(title="Event B", start_time=datetime(2024, 1, 15, 19, 0), source="Test"),
        Event(title="Event A", start_time=datetime(2024, 1, 15, 18, 0), source="Test"),  # Duplicate
    ]

    deduplicated = deduplicate_events(events)

    assert len(deduplicated) == 3
    assert deduplicated[0].title == "Event C"
    assert deduplicated[1].title == "Event A"
    assert deduplicated[2].title == "Event B"
