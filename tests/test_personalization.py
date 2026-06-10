"""Tests for LLM personalization layer."""

import json
from datetime import datetime

import pytz

from valencia_events.models import Event
from valencia_events.personalization import (
    DEFAULT_MISTRAL_MODEL,
    GeminiEventRanker,
    MistralEventRanker,
    PersonalizedSelection,
    _ranker_from_env,
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
            feedback_by_hash={"b": "Daytime, interactive, and easy to access."},
            used_llm=True,
        )


def test_load_family_profile_from_env(monkeypatch):
    monkeypatch.setenv("FAMILY_PROFILE_JSON", json.dumps({"audience": "test_family"}))
    profile = load_family_profile()
    assert profile["audience"] == "test_family"


def test_rank_events_for_family_fallback_without_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BACKEND", raising=False)
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


def test_gemini_ranker_falls_back_to_secondary_model(monkeypatch):
    from valencia_events.personalization import GeminiRankedEvent, GeminiRankingResponse

    ranker = GeminiEventRanker(
        api_key="x",
        model="gemini-3-flash-preview",
        fallback_model="gemini-2.5-pro",
    )
    events = [_event("A", "a"), _event("B", "b")]
    calls: list[str] = []

    def fake_invoke_model(*, model, family_profile, event_payload, limit):  # noqa: ANN001
        del family_profile, event_payload, limit
        calls.append(model)
        if model == "gemini-3-flash-preview":
            raise RuntimeError("503")
        return GeminiRankingResponse(
            summary="Fallback model worked.",
            selected_events=[
                GeminiRankedEvent(event_hash="b", reason="Better fit."),
                GeminiRankedEvent(event_hash="a", reason="Also suitable."),
            ],
            selected_event_hashes=["b", "a"],
        )

    monkeypatch.setattr(ranker, "_invoke_model", fake_invoke_model)
    selection = ranker.rank(events, family_profile={"audience": "test"}, limit=2)

    assert calls == ["gemini-3-flash-preview", "gemini-2.5-pro"]
    assert selection.used_llm is True
    assert [event.title for event in selection.events] == ["B", "A"]


def test_mistral_ranker_from_env_uses_default_model(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    monkeypatch.delenv("MISTRAL_MODEL", raising=False)
    monkeypatch.delenv("MISTRAL_FALLBACK_MODEL", raising=False)

    ranker = MistralEventRanker.from_env()

    assert ranker is not None
    assert ranker.model == DEFAULT_MISTRAL_MODEL
    assert ranker.fallback_model == ""


def test_ranker_from_env_prefers_mistral_when_available(monkeypatch):
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")

    ranker = _ranker_from_env()

    assert isinstance(ranker, MistralEventRanker)
    assert ranker.model == DEFAULT_MISTRAL_MODEL


def test_ranker_from_env_can_select_gemini(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "gemini")
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")

    ranker = _ranker_from_env()

    assert isinstance(ranker, GeminiEventRanker)
    assert not isinstance(ranker, MistralEventRanker)
