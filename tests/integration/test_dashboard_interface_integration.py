"""Integration tests for onboarding dashboard/interface flows."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from valencia_events.storage import EventStorage
from valencia_events.web import create_app


def _client_for_db(db_path: Path) -> TestClient:
    storage = EventStorage(str(db_path))
    app = create_app(storage)
    return TestClient(app)


def _register(
    client: TestClient,
    email: str,
    preferences_blob: str | None = None,
) -> dict:
    payload = {"email": email}
    if preferences_blob is not None:
        payload["preferences_blob"] = preferences_blob

    resp = client.post("/onboarding/register", json=payload)
    assert resp.status_code == 201
    return resp.json()


def _login(client: TestClient, email: str) -> dict:
    resp = client.post("/onboarding/login", json={"email": email})
    assert resp.status_code == 200
    return resp.json()


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_dashboard_flow_persists_across_app_restart(tmp_path):
    db_path = tmp_path / "dashboard.sqlite3"
    first_client = _client_for_db(db_path)

    registered = _register(
        first_client,
        "  Dashboard.User@Example.com ",
        preferences_blob='{"audience":"family"}',
    )
    first_token = registered["session_token"]

    me = first_client.get("/onboarding/me", headers=_auth_header(first_token))
    assert me.status_code == 200
    assert me.json()["email"] == "dashboard.user@example.com"
    assert me.json()["preferences"] == '{"audience":"family"}'

    updated = first_client.patch(
        "/onboarding/preferences",
        json={"preferences_blob": '{"interests":["museum","music"]}'},
        headers=_auth_header(first_token),
    )
    assert updated.status_code == 200
    assert updated.json()["preferences"] == '{"interests":["museum","music"]}'

    # Simulate API process restart while keeping the same database file.
    second_client = _client_for_db(db_path)
    login = _login(second_client, "dashboard.user@example.com")
    second_token = login["session_token"]

    me_after_restart = second_client.get(
        "/onboarding/me",
        headers=_auth_header(second_token),
    )
    assert me_after_restart.status_code == 200
    assert me_after_restart.json()["preferences"] == '{"interests":["museum","music"]}'


def test_dashboard_auth_boundary_conditions(tmp_path):
    client = _client_for_db(tmp_path / "auth.sqlite3")
    _register(client, "auth@example.com")

    no_header = client.get("/onboarding/me")
    assert no_header.status_code == 401
    assert no_header.json()["detail"] == "Authorization header required"

    wrong_scheme = client.get(
        "/onboarding/me",
        headers={"Authorization": "Basic abc123"},
    )
    assert wrong_scheme.status_code == 401
    assert wrong_scheme.json()["detail"] == "Bearer token required"

    bogus_token = client.get(
        "/onboarding/me",
        headers=_auth_header("not-a-valid-token"),
    )
    assert bogus_token.status_code == 401
    assert bogus_token.json()["detail"] == "Invalid or expired session"

    patch_with_bogus = client.patch(
        "/onboarding/preferences",
        json={"preferences_blob": '{"interests":["art"]}'},
        headers=_auth_header("not-a-valid-token"),
    )
    assert patch_with_bogus.status_code == 401
    assert patch_with_bogus.json()["detail"] == "Invalid or expired session"


def test_dashboard_multi_user_preference_isolation(tmp_path):
    client = _client_for_db(tmp_path / "isolation.sqlite3")

    user_a = _register(client, "user-a@example.com", preferences_blob='{"a":1}')
    user_b = _register(client, "user-b@example.com", preferences_blob='{"b":1}')

    token_a = user_a["session_token"]
    token_b = user_b["session_token"]

    update_a = client.patch(
        "/onboarding/preferences",
        json={"preferences_blob": '{"likes":["hiking"]}'},
        headers=_auth_header(token_a),
    )
    assert update_a.status_code == 200
    assert update_a.json()["email"] == "user-a@example.com"
    assert update_a.json()["preferences"] == '{"likes":["hiking"]}'

    me_b = client.get("/onboarding/me", headers=_auth_header(token_b))
    assert me_b.status_code == 200
    assert me_b.json()["email"] == "user-b@example.com"
    assert me_b.json()["preferences"] == '{"b":1}'


def test_dashboard_expired_session_rejected(tmp_path):
    db_path = tmp_path / "expired.sqlite3"
    client = _client_for_db(db_path)
    _register(client, "expires@example.com")

    storage = EventStorage(str(db_path))
    user = storage.get_user_by_email("expires@example.com")
    assert user is not None
    expired_token = storage.create_user_session(user.id, ttl_hours=-1)

    me = client.get("/onboarding/me", headers=_auth_header(expired_token))
    assert me.status_code == 401
    assert me.json()["detail"] == "Invalid or expired session"
