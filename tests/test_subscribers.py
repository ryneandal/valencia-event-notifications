"""Tests for scheduled subscriber-source selection and D1 loading."""

from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest

from valencia_events.subscribers import (
    D1Config,
    D1SubscriberStore,
    SubscriberLoadError,
    subscriber_source_from_env,
)


class _Response:
    def __init__(self, payload: object, *, raw: bytes | None = None) -> None:
        self._body = raw if raw is not None else json.dumps(payload).encode("utf-8")
        self.closed = False

    def read(self) -> bytes:
        return self._body

    def close(self) -> None:
        self.closed = True


def _success(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "success": True,
        "result": [{"success": True, "results": rows}],
    }


def _row(
    user_id: int,
    *,
    email: str | None = None,
    preferences_blob: str | None = None,
    is_active: int = 1,
) -> dict[str, object]:
    return {
        "id": user_id,
        "email": email or f"user{user_id}@example.com",
        "preferences_blob": preferences_blob,
        "is_active": is_active,
        "created_at": "2026-02-18 09:30:00",
    }


def _config(*, page_size: int = 100) -> D1Config:
    return D1Config(
        account_id="account-id",
        database_id="database-id",
        api_token="secret-token",
        api_base_url="https://api.example.test/client/v4",
        page_size=page_size,
    )


def test_d1_active_users_map_preferences_and_paginate():
    requests = []
    responses = [
        _Response(
            _success(
                [
                    _row(1, preferences_blob='{"interests":["music"]}'),
                    _row(2, preferences_blob=None),
                ]
            )
        ),
        _Response(_success([_row(4, email="last@example.com")])),
    ]

    def opener(request, timeout):  # noqa: ANN001
        requests.append((request, timeout))
        return responses.pop(0)

    store = D1SubscriberStore(_config(page_size=2), opener=opener)

    users = store.get_active_users()

    assert [user.id for user in users] == [1, 2, 4]
    assert users[0].preferences == '{"interests":["music"]}'
    assert users[1].preferences is None
    assert users[2].email == "last@example.com"
    assert all(user.is_active for user in users)
    assert [json.loads(request.data)["params"] for request, _ in requests] == [
        [0, 2],
        [2, 2],
    ]
    assert requests[0][0].full_url.endswith(
        "/accounts/account-id/d1/database/database-id/query"
    )
    assert requests[0][0].get_header("Authorization") == "Bearer secret-token"
    assert requests[0][1] == 20.0


def test_d1_empty_active_user_result():
    store = D1SubscriberStore(
        _config(),
        opener=lambda request, timeout: _Response(_success([])),  # noqa: ARG005
    )

    assert store.get_active_users() == []


def test_d1_user_lookup_normalizes_email():
    bodies = []

    def opener(request, timeout):  # noqa: ANN001, ARG001
        bodies.append(json.loads(request.data))
        return _Response(_success([_row(7, email="person@example.com")]))

    store = D1SubscriberStore(_config(), opener=opener)

    user = store.get_user_by_email(" Person@Example.com ")

    assert user is not None
    assert user.id == 7
    assert bodies[0]["params"] == ["person@example.com"]


@pytest.mark.parametrize(
    "response",
    [
        _Response({}, raw=b"not-json"),
        _Response({"success": False, "result": []}),
        _Response({"success": True, "result": []}),
        _Response({"success": True, "result": [{"success": False}]}),
        _Response(_success([{"id": 1}])),
    ],
)
def test_d1_invalid_responses_fail_closed(response):
    store = D1SubscriberStore(
        _config(),
        opener=lambda request, timeout: response,  # noqa: ARG005
    )

    with pytest.raises(SubscriberLoadError):
        store.get_active_users()


def test_d1_http_authentication_error_is_sanitized():
    def opener(request, timeout):  # noqa: ANN001, ARG001
        raise HTTPError(request.full_url, 401, "Unauthorized", hdrs=None, fp=None)

    store = D1SubscriberStore(_config(), opener=opener)

    with pytest.raises(SubscriberLoadError, match="HTTP 401") as exc_info:
        store.get_active_users()

    assert "secret-token" not in str(exc_info.value)


def test_d1_config_requires_all_environment_values(monkeypatch):
    monkeypatch.setenv("SUBSCRIBER_BACKEND", "d1")
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.setenv("CLOUDFLARE_D1_DATABASE_ID", "database-id")
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)

    with pytest.raises(SubscriberLoadError) as exc_info:
        subscriber_source_from_env(object())  # type: ignore[arg-type]

    assert "CLOUDFLARE_ACCOUNT_ID" in str(exc_info.value)
    assert "CLOUDFLARE_API_TOKEN" in str(exc_info.value)


def test_sqlite_is_the_local_subscriber_source(monkeypatch):
    local_storage = object()
    monkeypatch.setenv("SUBSCRIBER_BACKEND", "sqlite")

    source = subscriber_source_from_env(local_storage)  # type: ignore[arg-type]

    assert source.name == "sqlite"
    assert source.store is local_storage
    assert source.allow_recipient_fallback is True


def test_subscriber_source_must_be_selected_explicitly(monkeypatch):
    monkeypatch.delenv("SUBSCRIBER_BACKEND", raising=False)

    with pytest.raises(SubscriberLoadError, match="Missing SUBSCRIBER_BACKEND"):
        subscriber_source_from_env(object())  # type: ignore[arg-type]
