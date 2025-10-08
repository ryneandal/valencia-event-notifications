"""Tests for the database layer."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from valencia_events.database import EventDatabase
from valencia_events.models import Event


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    db = EventDatabase(db_path)
    yield db

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


def test_database_initialization(temp_db):
    """Test that database initializes correctly."""
    assert temp_db.db_path.exists()


def test_add_event(temp_db):
    """Test adding an event to the database."""
    event = Event(
        title="Test Event",
        description="A test event",
        location="Test Location",
        start_time=datetime(2024, 1, 15, 18, 0),
        source="Test Source",
    )

    result = temp_db.add_event(event)
    assert result is True  # Successfully added


def test_add_duplicate_event(temp_db):
    """Test that duplicate events are not added."""
    event1 = Event(
        title="Test Event",
        location="Test Location",
        start_time=datetime(2024, 1, 15, 18, 0),
        source="Test Source 1",
    )

    event2 = Event(
        title="Test Event",
        location="Test Location",
        start_time=datetime(2024, 1, 15, 18, 0),
        source="Test Source 2",
    )

    result1 = temp_db.add_event(event1)
    result2 = temp_db.add_event(event2)

    assert result1 is True
    assert result2 is False  # Duplicate not added


def test_add_multiple_events(temp_db):
    """Test adding multiple events at once."""
    events = [
        Event(title="Event 1", start_time=datetime(2024, 1, 15, 18, 0), source="Test Source"),
        Event(title="Event 2", start_time=datetime(2024, 1, 15, 19, 0), source="Test Source"),
        Event(title="Event 3", start_time=datetime(2024, 1, 15, 20, 0), source="Test Source"),
    ]

    added = temp_db.add_events(events)
    assert added == 3


def test_get_events_by_date(temp_db):
    """Test retrieving events by date."""
    # Add events for different dates
    event1 = Event(
        title="Event on Jan 15", start_time=datetime(2024, 1, 15, 18, 0), source="Test Source"
    )
    event2 = Event(
        title="Another Event on Jan 15",
        start_time=datetime(2024, 1, 15, 20, 0),
        source="Test Source",
    )
    event3 = Event(
        title="Event on Jan 16", start_time=datetime(2024, 1, 16, 18, 0), source="Test Source"
    )

    temp_db.add_event(event1)
    temp_db.add_event(event2)
    temp_db.add_event(event3)

    # Get events for Jan 15
    events_jan15 = temp_db.get_events_by_date(datetime(2024, 1, 15))
    assert len(events_jan15) == 2
    assert all(e.start_time.date() == datetime(2024, 1, 15).date() for e in events_jan15)

    # Get events for Jan 16
    events_jan16 = temp_db.get_events_by_date(datetime(2024, 1, 16))
    assert len(events_jan16) == 1


def test_get_all_events(temp_db):
    """Test retrieving all events."""
    events = [
        Event(title=f"Event {i}", start_time=datetime(2024, 1, 15 + i, 18, 0), source="Test")
        for i in range(5)
    ]

    temp_db.add_events(events)
    all_events = temp_db.get_all_events()

    assert len(all_events) == 5


def test_events_sorted_by_time(temp_db):
    """Test that retrieved events are sorted by start time."""
    events = [
        Event(title="Event 3", start_time=datetime(2024, 1, 15, 20, 0), source="Test"),
        Event(title="Event 1", start_time=datetime(2024, 1, 15, 18, 0), source="Test"),
        Event(title="Event 2", start_time=datetime(2024, 1, 15, 19, 0), source="Test"),
    ]

    temp_db.add_events(events)
    retrieved = temp_db.get_events_by_date(datetime(2024, 1, 15))

    assert retrieved[0].title == "Event 1"
    assert retrieved[1].title == "Event 2"
    assert retrieved[2].title == "Event 3"
