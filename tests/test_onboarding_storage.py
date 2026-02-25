"""Tests for user/session storage helpers."""

from __future__ import annotations

from valencia_events.storage import EventStorage


def test_create_user_session_and_lookup(tmp_path):
    storage = EventStorage(str(tmp_path / "session.db"))
    user = storage.create_user("test-session@example.com", preferences="{}")
    token = storage.create_user_session(user.id)

    current = storage.get_user_by_session_token(token)
    assert current is not None
    assert current.email == "test-session@example.com"


def test_update_user_preferences(tmp_path):
    storage = EventStorage(str(tmp_path / "prefs.db"))
    user = storage.create_user("prefs@example.com", preferences='{"old":true}')

    updated = storage.update_user_preferences(user.id, '{"new":"value"}')
    assert updated.preferences == '{"new":"value"}'

    fetched = storage.get_user_by_email("prefs@example.com")
    assert fetched is not None
    assert fetched.preferences == '{"new":"value"}'


def test_revoke_user_session(tmp_path):
    storage = EventStorage(str(tmp_path / "revoke.db"))
    user = storage.create_user("revoke@example.com")
    token = storage.create_user_session(user.id)

    assert storage.get_user_by_session_token(token) is not None
    assert storage.revoke_user_session(token) is True
    assert storage.get_user_by_session_token(token) is None
