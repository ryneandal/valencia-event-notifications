"""Tests for onboarding workflow (registration/login/preferences)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from valencia_events.storage import EventStorage
from valencia_events.web import create_app


def test_register_login_and_update_preferences(tmp_path):
    db_path = tmp_path / "onboarding.db"
    storage = EventStorage(str(db_path))
    app = create_app(storage)
    client = TestClient(app)

    register_resp = client.post(
        "/onboarding/register",
        json={
            "email": "user@example.com",
            "preferences_blob": '{"audience":"family"}',
        },
    )
    assert register_resp.status_code == 201
    registered = register_resp.json()
    assert registered["user"]["email"] == "user@example.com"
    assert registered["user"]["preferences"] == '{"audience":"family"}'
    assert registered["session_token"]

    login_resp = client.post(
        "/onboarding/login",
        json={"email": "user@example.com"},
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    session_token = login_data["session_token"]
    assert session_token

    me_resp = client.get(
        "/onboarding/me",
        headers={"Authorization": f"Bearer {session_token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "user@example.com"

    prefs_resp = client.patch(
        "/onboarding/preferences",
        json={"preferences_blob": '{"interests":["museums","hiking"]}'},
        headers={"Authorization": f"Bearer {session_token}"},
    )
    assert prefs_resp.status_code == 200
    assert prefs_resp.json()["preferences"] == '{"interests":["museums","hiking"]}'


def test_duplicate_registration_returns_conflict(tmp_path):
    storage = EventStorage(str(tmp_path / "duplicate.db"))
    app = create_app(storage)
    client = TestClient(app)

    first = client.post("/onboarding/register", json={"email": "dup@example.com"})
    assert first.status_code == 201

    second = client.post("/onboarding/register", json={"email": "dup@example.com"})
    assert second.status_code == 409


def test_me_requires_bearer_token(tmp_path):
    storage = EventStorage(str(tmp_path / "auth.db"))
    app = create_app(storage)
    client = TestClient(app)

    resp = client.get("/onboarding/me")
    assert resp.status_code == 401
