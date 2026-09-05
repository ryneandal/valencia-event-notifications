"""Tests for the local raw-event validation boundary."""

import pytest

from valencia_events.source_filters import should_keep_raw_event


@pytest.fixture
def complete_event() -> dict[str, str]:
    return {
        "title": "Concert at La Marina",
        "start": "12/10/2026 20:00",
        "url": "https://example.com/event",
        "source": "visit_valencia",
    }


def test_complete_raw_event_is_kept(complete_event: dict[str, str]):
    assert should_keep_raw_event(complete_event) is True


@pytest.mark.parametrize("field", ["title", "start", "url", "source"])
def test_every_required_field_is_enforced_once(
    complete_event: dict[str, str], field: str
):
    complete_event[field] = "  "
    assert should_keep_raw_event(complete_event) is False


def test_editorial_sources_still_require_event_like_dates(
    complete_event: dict[str, str],
):
    complete_event.update(source="valenciabonita", start="This weekend")
    assert should_keep_raw_event(complete_event) is False

    complete_event["start"] = "12 de octubre de 2026"
    assert should_keep_raw_event(complete_event) is True


def test_editorial_blocklist_is_preserved(complete_event: dict[str, str]):
    complete_event.update(source="valencia_secreta", title="Contenido patrocinado")
    assert should_keep_raw_event(complete_event) is False
