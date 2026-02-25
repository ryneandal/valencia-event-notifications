"""Tests for user-scoped digest runner helpers."""

from __future__ import annotations

from datetime import datetime

import pytz

from valencia_events.models import User
from valencia_events.runner import fire_digest_for_user

TZ = pytz.timezone("Europe/Madrid")


def _user(preferences: str | None = None, is_active: bool = True) -> User:
    return User(
        id=1,
        email="runner-user@example.com",
        preferences=preferences,
        is_active=is_active,
        created_at=TZ.localize(datetime(2025, 1, 1, 12, 0)),
    )


def _event(event_hash: str = "abc"):
    from valencia_events.models import Event

    return Event(
        title="Family Workshop",
        start=TZ.localize(datetime(2025, 10, 20, 11, 0)),
        url=f"https://example.com/{event_hash}",
        description="Interactive museum activity",
        source="test",
        event_hash=event_hash,
    )


def test_fire_digest_for_user_sends_to_specific_user(monkeypatch):
    from valencia_events import runner
    from valencia_events.personalization import PersonalizedSelection

    captured_profile = {}
    sent = {}

    def fake_rank(events, limit, ranker, family_profile):  # noqa: ANN001
        del limit, ranker
        captured_profile.update(family_profile)
        return PersonalizedSelection(
            events=events,
            summary="Fit for this user",
            feedback_by_hash={},
            used_llm=False,
        )

    def fake_send_email(subject, html_body, to_email):  # noqa: ANN001
        sent["subject"] = subject
        sent["html"] = html_body
        sent["to"] = to_email
        return True

    monkeypatch.setattr(runner, "rank_events_for_family", fake_rank)
    monkeypatch.setattr(runner, "send_email", fake_send_email)
    monkeypatch.setattr(runner, "build_html", lambda *args, **kwargs: "<html>ok</html>")

    user = _user(preferences='{"audience":"couple"}')
    ok = fire_digest_for_user(user=user, events=[_event()])

    assert ok is True
    assert sent["to"] == "runner-user@example.com"
    assert captured_profile["audience"] == "couple"


def test_fire_digest_for_user_skips_inactive_user(monkeypatch):
    from valencia_events import runner

    called = {"send": False}

    def fake_send_email(*args, **kwargs):  # noqa: ANN001
        called["send"] = True
        return True

    monkeypatch.setattr(runner, "send_email", fake_send_email)

    ok = fire_digest_for_user(user=_user(is_active=False), events=[_event()])
    assert ok is False
    assert called["send"] is False


def test_fire_digest_for_user_handles_empty_events():
    ok = fire_digest_for_user(user=_user(), events=[])
    assert ok is False
