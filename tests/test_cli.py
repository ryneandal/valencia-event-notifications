"""Regression tests for CLI behavior."""

from __future__ import annotations

from datetime import datetime

import pytz

from valencia_events.models import Event
from valencia_events.personalization import PersonalizedSelection

TZ = pytz.timezone("Europe/Madrid")


class _FakeStorage:
    def __init__(self):
        self.get_user_by_email_calls = 0

    def store_event(self, event):  # noqa: ANN001
        del event
        return True

    def get_user_by_email(self, email: str):  # noqa: ANN001
        del email
        self.get_user_by_email_calls += 1
        return None

    def get_active_users(self):
        return []

    def close(self):
        return None


def test_main_direct_invocation_does_not_use_typer_option_object(monkeypatch):
    from valencia_events import cli

    storage = _FakeStorage()
    event = Event(
        title="Tomorrow Event",
        start=TZ.localize(
            datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)
        ),
        url="https://example.com/tomorrow",
        description="desc",
        source="test",
    )

    monkeypatch.setattr(cli, "EventStorage", lambda: storage)
    monkeypatch.setattr(cli, "run_scrapers", lambda: [{"raw": "value"}])
    monkeypatch.setattr(cli, "normalize_raw", lambda raw: event)  # noqa: ARG005
    monkeypatch.setattr(cli, "filter_events_for_tomorrow", lambda events: events)
    monkeypatch.setattr(
        cli,
        "rank_events_for_family",
        lambda events, limit: PersonalizedSelection(  # noqa: ARG005
            events=events,
            summary=None,
            feedback_by_hash={},
            used_llm=False,
        ),
    )
    monkeypatch.setenv("SUBSCRIBER_BACKEND", "sqlite")
    monkeypatch.delenv("RECIPIENT_EMAIL", raising=False)

    cli.main()
    assert storage.get_user_by_email_calls == 0


def test_user_email_not_found_does_not_fallback_to_recipient(monkeypatch):
    from valencia_events import cli

    storage = _FakeStorage()
    event = Event(
        title="Tomorrow Event",
        start=TZ.localize(
            datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)
        ),
        url="https://example.com/tomorrow",
        description="desc",
        source="test",
    )
    send_called = {"value": False}

    def _send_email(*args, **kwargs):  # noqa: ANN002, ANN003
        del args, kwargs
        send_called["value"] = True
        return True

    monkeypatch.setattr(cli, "EventStorage", lambda: storage)
    monkeypatch.setattr(cli, "run_scrapers", lambda: [{"raw": "value"}])
    monkeypatch.setattr(cli, "normalize_raw", lambda raw: event)  # noqa: ARG005
    monkeypatch.setattr(cli, "filter_events_for_tomorrow", lambda events: events)
    monkeypatch.setattr(cli, "send_email", _send_email)
    monkeypatch.setenv("SUBSCRIBER_BACKEND", "sqlite")
    monkeypatch.setenv("RECIPIENT_EMAIL", "fallback@example.com")

    cli.main(user_email="missing@example.com")

    assert storage.get_user_by_email_calls == 1
    assert send_called["value"] is False
