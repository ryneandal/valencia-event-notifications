"""Tests for event normalization.

Test acceptance criteria:
- normalize_raw() converts variety of date strings to timezone-aware datetime
- Datetime is in Europe/Madrid timezone
- Handles ISO strings, Spanish date formats, RFC 822
- Returns valid Event pydantic model
"""

import pytest

from valencia_events.normalize import DateParseError, normalize_raw, parse_datetime


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
        """Test that invalid date strings raise the stable parse exception."""
        with pytest.raises(
            DateParseError, match="^Could not parse date: Invalid Date$"
        ):
            normalize_raw({"title": "Bad", "start": "Invalid Date"})


@pytest.mark.parametrize(
    ("raw_value", "expected_iso"),
    [
        ("29/03/2026 01:30", "2026-03-29T01:30:00+01:00"),
        ("29/03/2026 03:30", "2026-03-29T03:30:00+02:00"),
        ("25/10/2026 01:30", "2026-10-25T01:30:00+02:00"),
        ("25/10/2026 03:30", "2026-10-25T03:30:00+01:00"),
    ],
)
def test_dst_boundary_offsets_are_explicit(raw_value: str, expected_iso: str):
    assert parse_datetime(raw_value).isoformat() == expected_iso


@pytest.mark.parametrize(
    "raw_value",
    ["2026-03-29T02:30:00", "2026-10-25T02:30:00"],
)
def test_nonexistent_or_ambiguous_local_time_fails_without_guessing(raw_value: str):
    with pytest.raises(
        DateParseError,
        match=rf"^Invalid Europe/Madrid local time: {raw_value}$",
    ):
        parse_datetime(raw_value)


def test_ambiguous_numeric_date_is_always_day_first():
    parsed = parse_datetime("04/05/2026 18:15")
    assert parsed.isoformat() == "2026-05-04T18:15:00+02:00"


def test_unicode_context_and_spanish_month_name_are_preserved():
    parsed = parse_datetime("Miércoles, 12 de marzo de 2025 19:30")
    assert parsed.isoformat() == "2025-03-12T19:30:00+01:00"


def test_date_only_default_has_explicit_summer_offset():
    parsed = parse_datetime("10/07/2026")
    assert parsed.isoformat() == "2026-07-10T12:00:00+02:00"


def test_missing_optional_fields_receive_stable_defaults():
    event = normalize_raw(
        {
            "title": "Minimal Event",
            "start": "10/07/2026",
            "url": "https://example.com/minimal",
        }
    )
    assert event.description == ""
    assert event.source == "unknown"


@pytest.mark.parametrize(
    "raw_value",
    ["", "31/02/2026", "31.02.2026", "31 de febrero de 2026"],
)
def test_malformed_components_raise_the_documented_exception(raw_value: str):
    with pytest.raises(DateParseError, match="^Could not parse date:"):
        parse_datetime(raw_value)
