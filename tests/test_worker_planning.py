import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "cloudflare/worker/src"))

from worker_planning import (  # noqa: E402
    cleanup_planning,
    delivery_allowed,
    handle_planning_request,
)
from worker_time import available_preview_dates  # noqa: E402

from tests import test_worker_storage as storage_helpers  # noqa: E402
from tests.test_worker_storage import SQLiteD1, database  # noqa: E402

js_d1 = storage_helpers.js_d1


class Request:
    def __init__(self, payload=None):
        self.payload = payload or {}

    async def json(self):
        return self.payload


def setup(db_factory=SQLiteD1):
    connection = database()
    connection.executemany(
        "INSERT INTO users(id,email,is_active) VALUES (?,?,1)",
        [(1, "one@example.com"), (2, "two@example.com")],
    )
    connection.execute(
        "INSERT INTO events(id,event_key,title,start_at,url,source,time_precision) "
        "VALUES (1,'public-film','Public film','2026-10-24T18:00:00+02:00',"
        "'https://example.com/film','fixture','datetime')"
    )
    connection.commit()
    return connection, SimpleNamespace(
        DB=db_factory(connection), DIGEST_DELIVERY_ENABLED="false"
    )


def call(env, path="", method="GET", payload=None, user_id=1):
    response = asyncio.run(
        handle_planning_request(
            env, Request(payload), {"id": user_id}, "/api/planning" + path, method
        )
    )
    return response.status, json.loads(response.body)


def test_planning_defaults_have_real_dates_and_no_implicit_consent():
    _, env = setup()
    status, body = call(env)
    assert status == 200
    assert body["available_dates"] == available_preview_dates()
    assert body["delivery_days"] == list(range(7))
    assert body["delivery_enabled"] is False
    assert body["pilot"] == {"consented": False, "expires_at": None}
    assert body["saved_events"] == []
    assert "study_code" not in json.dumps(body)


def test_delivery_days_affect_digest_date_and_preserve_pause():
    connection, env = setup()
    assert call(env, "/delivery", "PATCH", {"days": [5, 0], "subscribed": True})[1] == {
        "delivery_days": [0, 5],
        "subscribed": True,
    }
    assert asyncio.run(delivery_allowed(env.DB, 1, "2026-10-24")) is True
    assert asyncio.run(delivery_allowed(env.DB, 1, "2026-10-25")) is False
    assert asyncio.run(delivery_allowed(env.DB, 2, "2026-10-25")) is True
    assert call(env, "/delivery", "PATCH", {"days": [], "subscribed": False})[0] == 200
    assert (
        connection.execute(
            "SELECT is_subscribed FROM subscriptions WHERE user_id=1"
        ).fetchone()[0]
        == 0
    )
    assert call(env)[1]["subscribed"] is False


@pytest.mark.parametrize(
    "days,subscribed",
    [
        ([True], True),
        ([1, 1], True),
        ([7], True),
        ([], True),
        ("Monday", True),
        ([0], 1),
    ],
)
def test_invalid_days_do_not_mutate(days, subscribed):
    connection, env = setup()
    assert (
        call(env, "/delivery", "PATCH", {"days": days, "subscribed": subscribed})[0]
        == 422
    )
    assert (
        connection.execute("SELECT COUNT(*) FROM delivery_preferences").fetchone()[0]
        == 0
    )


def test_saved_events_are_public_idempotent_and_account_scoped():
    connection, env = setup()
    for _ in range(2):
        status, result = call(env, "/saved", "POST", {"event_id": 1, "user_id": 2})
        assert status == 200
        assert len(result["saved_events"]) == 1
        assert set(result["saved_events"][0]) == {
            "id",
            "event_key",
            "title",
            "url",
            "start_at",
            "end_at",
            "time_precision",
            "location",
            "description",
            "source",
        }
    assert call(env, user_id=2)[1]["saved_events"] == []
    call(env, "/saved", "DELETE", {"event_id": 1}, user_id=2)
    assert len(call(env)[1]["saved_events"]) == 1
    call(env, "/saved", "DELETE", {"event_id": 1})
    assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    assert call(env)[1]["saved_events"] == []


def test_saved_event_cap_and_invalid_event():
    connection, env = setup()
    for index in range(2, 52):
        connection.execute(
            "INSERT INTO events(id,event_key,title,start_at,url,source) "
            "VALUES (?,?,?,?,?,?)",
            (
                index,
                f"event-{index}",
                "Film",
                "2026-10-24T18:00:00+02:00",
                "https://example.com/film",
                "fixture",
            ),
        )
    for index in range(1, 51):
        assert call(env, "/saved", "POST", {"event_id": index})[0] == 200
    assert call(env, "/saved", "POST", {"event_id": 51})[0] == 409
    assert call(env, "/saved", "POST", {"event_id": 1})[0] == 200
    assert call(env, "/saved", "POST", {"event_id": True})[0] == 422
    assert call(env, "/saved", "POST", {"event_id": 999})[0] == 404


def test_pilot_requires_consent_and_deletes_feedback_on_withdrawal():
    connection, env = setup()
    feedback = {
        "date": available_preview_dates()[0],
        "result_state": "empty",
        "useful": False,
    }
    assert call(env, "/feedback", "POST", feedback)[0] == 403
    assert (
        call(env, "/pilot", "PUT", {"consented": True})[1]["pilot"]["consented"] is True
    )
    assert (
        call(
            env,
            "/feedback",
            "POST",
            {**feedback, "email": "ignored@example.com", "event_id": 1},
        )[0]
        == 200
    )
    row = dict(connection.execute("SELECT * FROM pilot_feedback").fetchone())
    assert "user_id" not in row and "email" not in row and "event_id" not in row
    assert row["useful"] == 0 and row["action"] is None
    assert call(env, "/feedback", "POST", feedback, user_id=2)[0] == 403
    assert call(env, "/pilot", "PUT", {"consented": False})[0] == 200
    assert connection.execute("SELECT COUNT(*) FROM pilot_feedback").fetchone()[0] == 0


def test_expired_consent_cannot_submit_and_is_cleaned():
    connection, env = setup()
    call(env, "/pilot", "PUT", {"consented": True})
    call(
        env,
        "/feedback",
        "POST",
        {
            "date": available_preview_dates()[0],
            "result_state": "partial",
            "action": "copy",
        },
    )
    connection.execute(
        "UPDATE pilot_participants SET expires_at='2020-01-01T00:00:00+00:00'"
    )
    assert (
        call(
            env,
            "/feedback",
            "POST",
            {
                "date": available_preview_dates()[0],
                "result_state": "empty",
                "useful": True,
            },
        )[0]
        == 403
    )
    assert asyncio.run(cleanup_planning(env.DB)) == {
        "pilot_feedback": 1,
        "pilot_participants": 1,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"date": None},
        {"date": "2020-01-01"},
        {"useful": 1},
        {"result_state": []},
        {"action": "tracking"},
        {"useful": None, "action": None},
    ],
)
def test_feedback_validation(payload):
    _, env = setup()
    baseline = {
        "date": available_preview_dates()[0],
        "result_state": "empty",
        "useful": True,
    }
    assert call(env, "/feedback", "POST", {**baseline, **payload})[0] == 422


def test_nullable_feedback_crosses_pyodide_boundary(js_d1):
    connection, db = js_d1
    connection.execute("INSERT INTO users(id,email) VALUES (1,'test@example.com')")
    env = SimpleNamespace(DB=db)
    call(env, "/pilot", "PUT", {"consented": True})
    assert (
        call(
            env,
            "/feedback",
            "POST",
            {
                "date": available_preview_dates()[0],
                "result_state": "recommendations",
                "action": "calendar",
            },
        )[0]
        == 200
    )
