"""Tests for Gemini personalization layer."""

import json
from datetime import datetime

import pytz

from valencia_events.models import Event
from valencia_events.personalization import (
    GeminiEventRanker,
    PersonalizedSelection,
    load_family_profile,
    rank_events_for_family,
)

TZ = pytz.timezone("Europe/Madrid")


def _event(title: str, event_hash: str, hour: int = 10) -> Event:
    return Event(
        title=title,
        start=TZ.localize(datetime(2025, 10, 20, hour, 0)),
        url=f"https://example.com/{event_hash}",
        description="",
        source="test",
        event_hash=event_hash,
    )


class FakeRanker(GeminiEventRanker):
    """Fake ranker to avoid network calls."""

    def __init__(self):
        super().__init__(api_key="x", model="m")

    def rank(self, events, family_profile, limit):  # noqa: ANN001
        del family_profile
        return PersonalizedSelection(
            events=list(reversed(events))[:limit],
            summary="Picked family-friendly options.",
            used_llm=True,
        )


def test_load_family_profile_from_env(monkeypatch):
    monkeypatch.setenv("FAMILY_PROFILE_JSON", json.dumps({"audience": "test_family"}))
    profile = load_family_profile()
    assert profile["audience"] == "test_family"


def test_rank_events_for_family_fallback_without_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    events = [_event("B", "b", 11), _event("A", "a", 10)]

    selection = rank_events_for_family(events, limit=1)

    assert len(selection.events) == 1
    assert selection.used_llm is False


def test_rank_events_for_family_with_custom_ranker():
    events = [_event("A", "a"), _event("B", "b")]
    selection = rank_events_for_family(events, limit=2, ranker=FakeRanker())
    assert selection.used_llm is True
    assert selection.summary == "Picked family-friendly options."
    assert [event.title for event in selection.events] == ["B", "A"]
