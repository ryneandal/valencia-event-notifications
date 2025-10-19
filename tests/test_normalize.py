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
        # TODO: Implement test
        # from normalize import normalize_raw
        # raw = {
        #     "title": "Test Event",
        #     "start": "2025-10-12T20:00:00+02:00",
        #     "url": "https://example.com",
        #     "description": "Test",
        #     "source": "test"
        # }
        # event = normalize_raw(raw)
        # assert event.start.tzinfo is not None
        # assert event.start.tzinfo.zone == "Europe/Madrid"
        pytest.skip("normalize_raw() not yet implemented")

    def test_normalize_spanish_date_format(self):
        """Test normalization of Spanish date format."""
        # TODO: Test format like "12 de octubre de 2025 20:00"
        pytest.skip("normalize_raw() not yet implemented")

    def test_normalize_numeric_date_format(self):
        """Test normalization of numeric date format."""
        # TODO: Test format like "12/10/2025 20:00"
        pytest.skip("normalize_raw() not yet implemented")

    def test_normalize_rfc822_format(self):
        """Test normalization of RFC 822 format (RSS)."""
        # TODO: Test format from RSS feeds
        pytest.skip("normalize_raw() not yet implemented")

    def test_invalid_date_raises_error(self):
        """Test that invalid date string raises ValueError."""
        # TODO: Test error handling
        pytest.skip("normalize_raw() not yet implemented")
