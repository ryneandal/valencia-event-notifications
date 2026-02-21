"""Tests for event normalization.

Test acceptance criteria:
- normalize_raw() converts variety of date strings to timezone-aware datetime
- Datetime is in Europe/Madrid timezone
- Handles ISO strings, Spanish date formats, RFC 822
- Returns valid Event pydantic model
"""

import pytest


class TestNormalize:
    """Test suite for event normalization."""

    def test_normalize_iso_datetime(self):
        """Test normalization of ISO 8601 datetime string."""
        from valencia_events.normalize import normalize_raw

        raw = {
            "title": "Test Event",
            "start": "2025-10-12T20:00:00+02:00",
            "url": "https://example.com",
            "description": "Test",
            "source": "test",
        }
        event = normalize_raw(raw)
        assert event.start.tzinfo is not None
        # Should be converted to Europe/Madrid
        assert str(event.start.tzinfo) == "Europe/Madrid"

    def test_normalize_spanish_date_format(self):
        """Test normalization of Spanish date format."""
        from valencia_events.normalize import normalize_raw

        raw = {
            "title": "Spanish Event",
            "start": "12 de octubre de 2025 20:00",
            "url": "https://example.com",
        }
        event = normalize_raw(raw)
        assert event.start.year == 2025
        assert event.start.month == 10
        assert event.start.day == 12
        assert event.start.hour == 20

    def test_normalize_numeric_date_format(self):
        """Test normalization of numeric date format."""
        from valencia_events.normalize import normalize_raw

        raw = {
            "title": "Numeric Event",
            "start": "12/10/2025 20:00",
            "url": "https://example.com",
        }
        event = normalize_raw(raw)
        assert event.start.year == 2025
        assert event.start.month == 10
        assert event.start.day == 12

    def test_normalize_rfc822_format(self):
        """Test normalization of RFC 822 format (RSS)."""
        from valencia_events.normalize import normalize_raw

        raw = {
            "title": "RSS Event",
            "start": "Sat, 12 Oct 2025 20:00:00 +0200",
            "url": "https://example.com",
        }
        event = normalize_raw(raw)
        assert event.start.year == 2025
        assert event.start.month == 10
        assert event.start.day == 12
        assert event.start.hour == 20

    def test_date_only_defaults_to_noon(self):
        """Test date-only values default to 12:00 in Europe/Madrid."""
        from valencia_events.normalize import normalize_raw

        raw = {
            "title": "Date Only Event",
            "start": "12/10/2025",
            "url": "https://example.com/date-only",
        }
        event = normalize_raw(raw)
        assert event.start.hour == 12
        assert event.start.minute == 0

    def test_invalid_date_raises_error(self):
        """Test that invalid date string raises ValueError."""
        from valencia_events.normalize import normalize_raw

        with pytest.raises(ValueError):
            normalize_raw({"title": "Bad", "start": "Invalid Date"})
