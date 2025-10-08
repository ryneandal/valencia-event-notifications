"""Tests for email digest generation."""

from datetime import datetime

from valencia_events.email_digest import generate_html_digest
from valencia_events.models import Event


def test_generate_html_digest_with_events():
    """Test generating HTML digest with events."""
    events = [
        Event(
            title="Test Event 1",
            description="First test event",
            location="Location 1",
            start_time=datetime(2024, 1, 15, 18, 0),
            url="https://example.com/event1",
            source="Test Source",
            neighborhood="La Roqueta",
        ),
        Event(
            title="Test Event 2",
            description="Second test event",
            location="Location 2",
            start_time=datetime(2024, 1, 15, 20, 0),
            url="https://example.com/event2",
            source="Test Source",
            neighborhood="Russafa",
        ),
    ]

    date = datetime(2024, 1, 15)
    html = generate_html_digest(events, date)

    # Check that HTML contains event details
    assert "Test Event 1" in html
    assert "Test Event 2" in html
    assert "Location 1" in html
    assert "Location 2" in html
    assert "La Roqueta" in html
    assert "Russafa" in html
    assert "https://example.com/event1" in html
    assert "https://example.com/event2" in html
    assert "First test event" in html
    assert "Second test event" in html
    assert "Found 2 events" in html


def test_generate_html_digest_no_events():
    """Test generating HTML digest with no events."""
    events = []
    date = datetime(2024, 1, 15)
    html = generate_html_digest(events, date)

    # Check that HTML indicates no events
    assert "No Events Tomorrow" in html
    assert "There are no events scheduled" in html


def test_generate_html_digest_minimal_event():
    """Test generating HTML digest with minimal event data."""
    events = [
        Event(title="Minimal Event", start_time=datetime(2024, 1, 15, 18, 0), source="Test Source")
    ]

    date = datetime(2024, 1, 15)
    html = generate_html_digest(events, date)

    # Check that HTML handles missing fields gracefully
    assert "Minimal Event" in html
    assert "TBD" in html  # Default location text


def test_generate_html_digest_sorts_by_time():
    """Test that events are sorted by start time in the digest."""
    events = [
        Event(title="Event at 8 PM", start_time=datetime(2024, 1, 15, 20, 0), source="Test"),
        Event(title="Event at 6 PM", start_time=datetime(2024, 1, 15, 18, 0), source="Test"),
        Event(title="Event at 7 PM", start_time=datetime(2024, 1, 15, 19, 0), source="Test"),
    ]

    date = datetime(2024, 1, 15)
    html = generate_html_digest(events, date)

    # Check order by finding positions
    pos_6pm = html.find("Event at 6 PM")
    pos_7pm = html.find("Event at 7 PM")
    pos_8pm = html.find("Event at 8 PM")

    assert pos_6pm < pos_7pm < pos_8pm


def test_generate_html_digest_valid_html():
    """Test that generated HTML is valid (has basic structure)."""
    events = [
        Event(title="Test Event", start_time=datetime(2024, 1, 15, 18, 0), source="Test Source")
    ]

    date = datetime(2024, 1, 15)
    html = generate_html_digest(events, date)

    # Check for basic HTML structure
    assert "<html>" in html
    assert "</html>" in html
    assert "<head>" in html
    assert "</head>" in html
    assert "<body>" in html
    assert "</body>" in html
    assert "<style>" in html
    assert "</style>" in html
