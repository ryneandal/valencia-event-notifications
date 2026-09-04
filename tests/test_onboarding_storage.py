"""Tests for retained local user storage helpers."""

from __future__ import annotations

from valencia_events.storage import EventStorage


def test_update_user_preferences(tmp_path):
    storage = EventStorage(str(tmp_path / "prefs.db"))
    user = storage.create_user("prefs@example.com", preferences='{"old":true}')

    updated = storage.update_user_preferences(user.id, '{"new":"value"}')
    assert updated.preferences == '{"new":"value"}'

    fetched = storage.get_user_by_email("prefs@example.com")
    assert fetched is not None
    assert fetched.preferences == '{"new":"value"}'
