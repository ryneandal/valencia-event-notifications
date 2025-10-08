"""Tests for the Event model."""

from datetime import datetime

from valencia_events.models import Event


def test_event_creation():
    """Test creating an Event instance."""
    event = Event(
        title="Test Event",
        description="A test event",
        location="Test Location",
        start_time=datetime(2024, 1, 15, 18, 0),
        end_time=datetime(2024, 1, 15, 20, 0),
        url="https://example.com",
        source="Test Source",
        neighborhood="La Roqueta",
    )

    assert event.title == "Test Event"
    assert event.description == "A test event"
    assert event.location == "Test Location"
    assert event.start_time == datetime(2024, 1, 15, 18, 0)
    assert event.end_time == datetime(2024, 1, 15, 20, 0)
    assert event.url == "https://example.com"
    assert event.source == "Test Source"
    assert event.neighborhood == "La Roqueta"


def test_event_minimal():
    """Test creating an Event with minimal required fields."""
    event = Event(
        title="Minimal Event", start_time=datetime(2024, 1, 15, 18, 0), source="Test Source"
    )

    assert event.title == "Minimal Event"
    assert event.description is None
    assert event.location is None
    assert event.end_time is None
    assert event.url is None
    assert event.neighborhood is None


def test_event_equality():
    """Test event equality for deduplication."""
    event1 = Event(
        title="Test Event",
        start_time=datetime(2024, 1, 15, 18, 0),
        location="Test Location",
        source="Source 1",
    )

    event2 = Event(
        title="Test Event",
        start_time=datetime(2024, 1, 15, 18, 0),
        location="Test Location",
        source="Source 2",
    )

    # Should be equal despite different sources
    assert event1 == event2


def test_event_inequality_different_title():
    """Test that events with different titles are not equal."""
    event1 = Event(
        title="Event 1",
        start_time=datetime(2024, 1, 15, 18, 0),
        location="Test Location",
        source="Test Source",
    )

    event2 = Event(
        title="Event 2",
        start_time=datetime(2024, 1, 15, 18, 0),
        location="Test Location",
        source="Test Source",
    )

    assert event1 != event2


def test_event_inequality_different_time():
    """Test that events at different times are not equal."""
    event1 = Event(
        title="Test Event",
        start_time=datetime(2024, 1, 15, 18, 0),
        location="Test Location",
        source="Test Source",
    )

    event2 = Event(
        title="Test Event",
        start_time=datetime(2024, 1, 15, 19, 0),
        location="Test Location",
        source="Test Source",
    )

    assert event1 != event2


def test_event_hash():
    """Test that events can be hashed for use in sets."""
    event1 = Event(
        title="Test Event",
        start_time=datetime(2024, 1, 15, 18, 0),
        location="Test Location",
        source="Source 1",
    )

    event2 = Event(
        title="Test Event",
        start_time=datetime(2024, 1, 15, 18, 0),
        location="Test Location",
        source="Source 2",
    )

    # Should have same hash
    assert hash(event1) == hash(event2)

    # Can be added to a set
    event_set = {event1, event2}
    assert len(event_set) == 1  # Deduplicated


def test_event_case_insensitive_title():
    """Test that title comparison is case-insensitive."""
    event1 = Event(
        title="Test Event",
        start_time=datetime(2024, 1, 15, 18, 0),
        location="Test Location",
        source="Test Source",
    )

    event2 = Event(
        title="test event",
        start_time=datetime(2024, 1, 15, 18, 0),
        location="Test Location",
        source="Test Source",
    )

    assert event1 == event2
    assert hash(event1) == hash(event2)
