"""Tests for event storage layer.

Test acceptance criteria:
- Database creation works
- Events can be stored
- Duplicate events are detected and not inserted twice
- Events can be retrieved by date
"""

import tempfile
from pathlib import Path

import pytest


class TestEventStorage:
    """Test suite for event storage."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        # Cleanup
        Path(db_path).unlink(missing_ok=True)

    @pytest.fixture
    def storage(self, temp_db):
        """Create storage instance with temp database."""
        from valencia_events.storage import EventStorage
        return EventStorage(temp_db)

    @pytest.fixture
    def sample_event(self):
        """Create sample event for testing."""
        from datetime import datetime
        from valencia_events.models import Event
        return Event(
            title="Test Event",
            start=datetime(2025, 10, 12, 20, 0),
            url="https://example.com/test",
            description="Test description",
            source="test"
        )

    def test_store_event(self, storage, sample_event):
        """Test storing an event."""
        result = storage.store_event(sample_event)
        assert result is True

    def test_duplicate_detection(self, storage, sample_event):
        """Test that duplicate events are not inserted twice."""
        from valencia_events.storage import compute_event_hash
        sample_event.event_hash = compute_event_hash(sample_event)
        
        # Store first time
        result1 = storage.store_event(sample_event)
        assert result1 is True
        
        # Store second time (should be duplicate)
        result2 = storage.store_event(sample_event)
        assert result2 is False

    def test_get_events_for_date(self, storage, sample_event):
        """Test retrieving events for a specific date."""
        storage.store_event(sample_event)
        
        # Match date
        events = storage.get_events_for_date(sample_event.start)
        assert len(events) == 1
        assert events[0].title == sample_event.title
        
        # Mismatch date
        from datetime import datetime, timedelta
        events_empty = storage.get_events_for_date(sample_event.start + timedelta(days=1))
        assert len(events_empty) == 0
