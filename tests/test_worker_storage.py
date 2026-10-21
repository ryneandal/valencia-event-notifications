import asyncio
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

WORKER_PATH = (
    Path(__file__).resolve().parents[1] / "cloudflare" / "worker" / "src" / "index.py"
)
sys.path.insert(0, str(WORKER_PATH.parent))

spec = importlib.util.spec_from_file_location(
    "cloudflare_worker_storage", WORKER_PATH.parent / "worker_storage.py"
)
storage = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(storage)


class SQLiteD1:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def prepare(self, sql: str):
        return SQLiteD1Statement(self.connection, sql)


class SQLiteD1Statement:
    def __init__(self, connection: sqlite3.Connection, sql: str):
        self.connection = connection
        self.sql = sql
        self.params = ()

    def bind(self, *params):
        self.params = params
        return self

    async def run(self):
        cursor = self.connection.execute(self.sql, self.params)
        self.connection.commit()
        return {
            "success": True,
            "meta": {"changes": max(cursor.rowcount, 0)},
        }

    async def first(self):
        cursor = self.connection.execute(self.sql, self.params)
        row = cursor.fetchone()
        return dict(row) if row is not None else None

    async def all(self):
        cursor = self.connection.execute(self.sql, self.params)
        return {"success": True, "results": [dict(row) for row in cursor.fetchall()]}


def database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript((WORKER_PATH.parent / "schema.sql").read_text())
    return connection


def seed_user_and_run(connection: sqlite3.Connection) -> tuple[int, int]:
    user = connection.execute(
        "INSERT INTO users (email, is_active) VALUES ('reader@example.com', 1)"
    )
    run = connection.execute(
        "INSERT INTO digest_runs (digest_date) VALUES ('2026-09-05')"
    )
    connection.commit()
    return int(user.lastrowid), int(run.lastrowid)


@pytest.fixture
def js_d1(monkeypatch):
    """Model Pyodide None -> undefined and D1's rejection of undefined."""
    js_null = object()
    ffi = SimpleNamespace(jsnull=js_null)
    monkeypatch.setitem(sys.modules, "pyodide", SimpleNamespace(ffi=ffi))
    monkeypatch.setitem(sys.modules, "pyodide.ffi", ffi)

    class JSStatement(SQLiteD1Statement):
        def bind(self, *params):
            if any(value is None for value in params):
                raise TypeError("D1_TYPE_ERROR: Type 'undefined' not supported")
            return super().bind(
                *(None if value is js_null else value for value in params)
            )

    class JSD1(SQLiteD1):
        def prepare(self, sql):
            return JSStatement(self.connection, sql)

    connection = database()
    yield connection, JSD1(connection)
    connection.close()


@pytest.mark.parametrize("p_yes", [0.99, 0.5, None])
def test_jev_audit_persists_nullable_fields_across_js_boundary(js_d1, p_yes):
    from worker_jev import attach_event, fallback_evaluation
    from worker_relevance import score_answers

    connection, db = js_d1
    user_id, run_id = seed_user_and_run(connection)
    event = {"event_key": "film", "title": "Cinema", "url": "https://example.com/film"}
    event_id = connection.execute(
        """
        INSERT INTO events (event_key, title, start_at, url, source)
        VALUES ('film', 'Cinema', '2026-09-05', 'https://example.com/film', 'fixture')
        """
    ).lastrowid
    evaluation = (
        fallback_evaluation(event, ["film"], "provider_unavailable")
        if p_yes is None
        else attach_event(
            event,
            score_answers(
                ["film"], {"event_type:film": {"type": "noul", "noul": p_yes}}
            ),
            "jev-1.13.0",
        )
    )

    asyncio.run(
        storage.record_jev_evaluation(
            db,
            digest_run_id=run_id,
            user_id=user_id,
            event_id=event_id,
            evaluation=evaluation,
        )
    )

    row = dict(connection.execute("SELECT * FROM jev_evaluations").fetchone())
    for field in ("model", "irrelevance_score", "decision", "status", "error_code"):
        assert row[field] == evaluation[field]
    assert json.loads(row["components"]) == evaluation["components"]


def test_delivery_without_provider_id_persists_sql_null_across_js_boundary(js_d1):
    connection, db = js_d1
    user_id, run_id = seed_user_and_run(connection)
    assert asyncio.run(storage.claim_delivery(db, run_id, user_id))

    assert asyncio.run(storage.mark_delivery_sent(db, run_id, user_id, None))

    row = connection.execute(
        "SELECT status, provider_message_id FROM deliveries"
    ).fetchone()
    assert tuple(row) == ("sent", None)


def test_event_upsert_has_stable_identity_and_deduplicates():
    connection = database()
    db = SQLiteD1(connection)
    event = {
        "title": "Concert a la Marina",
        "start_at": "2026-09-05T20:00:00+02:00",
        "url": "https://example.com/concert",
        "description": "Original description",
        "source": "fixture",
    }

    first_key = asyncio.run(storage.upsert_event(db, **event))
    second_key = asyncio.run(
        storage.upsert_event(db, **{**event, "description": "Updated description"})
    )

    row = connection.execute("SELECT event_key, description FROM events").fetchone()
    assert (
        first_key
        == second_key
        == storage.event_key(event["title"], event["start_at"], event["url"])
    )
    assert tuple(row) == (first_key, "Updated description")
    assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1


def test_event_batch_lookup_uses_collector_keys_not_original_start_date():
    connection = database()
    db = SQLiteD1(connection)
    ongoing = {
        "title": "Ongoing exhibition",
        "start_at": "2026-09-03T11:00:00+02:00",
        "url": "https://example.com/ongoing",
        "description": "Open through the digest date.",
        "source": "fixture",
    }
    unrelated = {
        "title": "Unrelated event",
        "start_at": "2026-09-05T20:00:00+02:00",
        "url": "https://example.com/unrelated",
        "description": "Not selected by this collection run.",
        "source": "fixture",
    }
    ongoing_key = asyncio.run(storage.upsert_event(db, **ongoing))
    asyncio.run(storage.upsert_event(db, **unrelated))

    events = asyncio.run(storage.list_events_by_keys(db, [ongoing_key, ongoing_key]))

    assert [event["title"] for event in events] == ["Ongoing exhibition"]
    assert asyncio.run(storage.list_events_by_keys(db, [])) == []


def test_active_subscriber_selection_excludes_paused_and_unverified_users():
    connection = database()
    db = SQLiteD1(connection)
    active = connection.execute(
        "INSERT INTO users (email, is_active) VALUES ('active@example.com', 1)"
    )
    paused = connection.execute(
        "INSERT INTO users (email, is_active) VALUES ('paused@example.com', 1)"
    )
    connection.execute(
        "INSERT INTO users (email, is_active) VALUES ('pending@example.com', 0)"
    )
    connection.execute(
        "INSERT INTO subscriptions (user_id, is_subscribed) VALUES (?, 0)",
        (paused.lastrowid,),
    )
    connection.commit()

    subscribers = asyncio.run(storage.list_active_subscribers(db))

    assert subscribers == [
        {
            "id": active.lastrowid,
            "email": "active@example.com",
            "preferences_blob": None,
        }
    ]


def test_digest_run_and_recommendation_store_model_provenance():
    connection = database()
    db = SQLiteD1(connection)
    user_id, _ = seed_user_and_run(connection)
    event_id = connection.execute(
        """
        INSERT INTO events (event_key, title, start_at, url, source)
        VALUES ('event-one', 'Event one', '2026-09-05T10:00:00+02:00',
                'https://example.com/one', 'fixture')
        """
    ).lastrowid
    connection.commit()

    run = asyncio.run(
        storage.get_or_create_digest_run(
            db,
            digest_date="2026-09-05",
            scheduled_for="2026-09-05T08:00:00Z",
        )
    )
    asyncio.run(
        storage.record_recommendation(
            db,
            digest_run_id=run["id"],
            user_id=user_id,
            event_id=event_id,
            position=1,
            relevance_reason="A strong match for live music.",
            model_id="nvidia/nemotron-3-ultra-550b-a55b:free",
            used_fallback=False,
        )
    )

    recommendation = connection.execute(
        "SELECT position, relevance_reason, model_id, used_fallback "
        "FROM recommendations"
    ).fetchone()
    assert tuple(recommendation) == (
        1,
        "A strong match for live music.",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        0,
    )


def test_failed_delivery_can_be_retried():
    connection = database()
    db = SQLiteD1(connection)
    user_id, run_id = seed_user_and_run(connection)

    assert asyncio.run(storage.claim_delivery(db, run_id, user_id)) is True
    assert (
        asyncio.run(
            storage.mark_delivery_failed(
                db,
                run_id,
                user_id,
                "mailgun timeout\nsecret details are not persisted beyond the limit",
            )
        )
        is True
    )
    assert asyncio.run(storage.claim_delivery(db, run_id, user_id)) is False
    connection.execute(
        "UPDATE deliveries SET updated_at = datetime('now', '-6 minutes')"
    )
    connection.commit()
    assert asyncio.run(storage.claim_delivery(db, run_id, user_id)) is True

    delivery = connection.execute(
        "SELECT status, attempt_count, last_error_code FROM deliveries"
    ).fetchone()
    assert tuple(delivery) == ("pending", 2, None)


def test_failed_delivery_backoff_has_a_bounded_attempt_count():
    connection = database()
    db = SQLiteD1(connection)
    user_id, run_id = seed_user_and_run(connection)

    assert asyncio.run(storage.claim_delivery(db, run_id, user_id)) is True
    for expected_attempt in (2, 3):
        assert asyncio.run(
            storage.mark_delivery_failed(db, run_id, user_id, "mailgun_http_503")
        )
        connection.execute(
            "UPDATE deliveries SET updated_at = datetime('now', '-20 minutes')"
        )
        connection.commit()
        assert asyncio.run(storage.claim_delivery(db, run_id, user_id)) is True
        attempt = connection.execute("SELECT attempt_count FROM deliveries").fetchone()[
            0
        ]
        assert attempt == expected_attempt

    assert asyncio.run(
        storage.mark_delivery_failed(db, run_id, user_id, "mailgun_http_503")
    )
    connection.execute("UPDATE deliveries SET updated_at = datetime('now', '-1 day')")
    connection.commit()
    assert asyncio.run(storage.claim_delivery(db, run_id, user_id)) is False


def test_successful_delivery_cannot_be_claimed_twice():
    connection = database()
    db = SQLiteD1(connection)
    user_id, run_id = seed_user_and_run(connection)

    assert asyncio.run(storage.claim_delivery(db, run_id, user_id)) is True
    assert (
        asyncio.run(
            storage.mark_delivery_sent(db, run_id, user_id, "mailgun-message-id")
        )
        is True
    )
    assert asyncio.run(storage.claim_delivery(db, run_id, user_id)) is False
    assert (
        asyncio.run(
            storage.mark_delivery_sent(db, run_id, user_id, "duplicate-message-id")
        )
        is False
    )

    delivery = connection.execute(
        "SELECT status, attempt_count, provider_message_id FROM deliveries"
    ).fetchone()
    assert tuple(delivery) == ("sent", 1, "mailgun-message-id")
    assert connection.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0] == 1


def test_retention_cleanup_removes_history_before_unreferenced_events():
    connection = database()
    db = SQLiteD1(connection)
    user_id, run_id = seed_user_and_run(connection)
    event_id = connection.execute(
        """
        INSERT INTO events (
          event_key, title, start_at, url, source, last_seen_at
        ) VALUES (
          'old-event', 'Old event', '2026-06-01T10:00:00+02:00',
          'https://example.com/old', 'fixture', '2026-06-01T08:00:00Z'
        )
        """
    ).lastrowid
    connection.execute(
        """
        INSERT INTO recommendations (
          digest_run_id, user_id, event_id, position,
          relevance_reason, model_id, used_fallback
        ) VALUES (?, ?, ?, 1, 'Good fit', 'fallback', 1)
        """,
        (run_id, user_id, event_id),
    )
    connection.execute(
        "INSERT INTO deliveries (digest_run_id, user_id, status) VALUES (?, ?, 'sent')",
        (run_id, user_id),
    )
    connection.commit()

    deleted = asyncio.run(
        storage.delete_expired_history(
            db,
            digest_date_before="2026-09-06",
            event_last_seen_before="2026-08-07T00:00:00Z",
        )
    )

    assert deleted == {
        "deliveries": 1,
        "recommendations": 1,
        "digest_runs": 1,
        "events": 1,
    }


def test_jev_cache_reuses_identity_free_answers_and_fetches_new_selections():
    import worker_jev as jev

    connection = database()
    calls = []
    event = {
        "event_key": "jazz",
        "title": "Jazz",
        "url": "https://example.com/jazz",
        "description": "Jazz concert",
    }

    async def fake(body):
        calls.append(body)
        return {
            "model": body["model"],
            "answers": {
                key: {
                    "type": "noul",
                    "noul": 0.94 if key.endswith("live_music") else 0.08,
                }
                for key in body["questions"]
            },
        }

    env = SimpleNamespace(DB=SQLiteD1(connection), JEV_MODE="shadow", JEV_FETCH=fake)
    music = asyncio.run(jev.evaluate_event(env, event, ["live_music"]))
    food = asyncio.run(
        jev.evaluate_event(env, {**event, "user_id": 99}, ["food_drink"])
    )
    both = asyncio.run(jev.evaluate_event(env, event, ["live_music", "food_drink"]))
    assert music["decision"] == both["decision"] == "eligible"
    assert food["decision"] == "irrelevant"
    assert len(calls) == 2
    assert all(len(body["questions"]) == 1 for body in calls)
    assert "user_id" not in json.dumps(calls)
    assert (
        connection.execute("SELECT COUNT(*) FROM jev_answer_cache").fetchone()[0] == 2
    )
    asyncio.run(
        jev.evaluate_event(
            env, {**event, "description": "Changed event"}, ["food_drink"]
        )
    )
    env.JEV_MODEL = "jev-1.14.0"
    asyncio.run(jev.evaluate_event(env, event, ["food_drink"]))
    assert len(calls) == 4


def test_jev_cache_expiry_and_invalid_cached_answer_cannot_exclude():
    import worker_jev as jev

    connection = database()
    db = SQLiteD1(connection)
    answers = {"event_type:film": {"type": "noul", "noul": 0.0}}
    asyncio.run(storage.save_jev_answers(db, "old", jev.DEFAULT_MODEL, answers))
    connection.execute("UPDATE jev_answer_cache SET created_at = '2000-01-01'")
    connection.commit()
    assert asyncio.run(storage.load_jev_answers(db, "old", jev.DEFAULT_MODEL)) == {}

    # Cached data is validated just like a fresh response before scoring.
    async def bad_cache(*_args):
        return {"event_type:film": {"type": "noul", "noul": True}}

    async def unavailable(_body):
        raise jev.ProviderHTTPError(401)

    event = {"event_key": "one", "title": "Title", "url": "https://example.com/one"}
    from unittest.mock import patch

    with patch.object(jev, "load_jev_answers", bad_cache):
        result = asyncio.run(
            jev.evaluate_event(
                SimpleNamespace(DB=db, JEV_MODE="filter", JEV_FETCH=unavailable),
                event,
                ["film"],
            )
        )
    assert result["status"] == "fallback"
    assert result["decision"] == "unknown"


def test_jev_evaluation_retention_protects_rejected_event_until_run_expires():
    from worker_jev import attach_event
    from worker_relevance import score_answers

    connection = database()
    db = SQLiteD1(connection)
    user_id, run_id = seed_user_and_run(connection)
    event = {"event_key": "reject", "title": "Tour", "url": "https://example.com/tour"}
    event_id = connection.execute(
        "INSERT INTO events(event_key,title,url,start_at,source,last_seen_at) VALUES ('reject','Tour','https://example.com/tour','2026-06-01','fixture','2026-06-01')"
    ).lastrowid
    evaluation = attach_event(
        event,
        score_answers(["film"], {"event_type:film": {"type": "noul", "noul": 0}}),
        "jev-1.13.0",
    )
    asyncio.run(
        storage.record_jev_evaluation(
            db,
            digest_run_id=run_id,
            user_id=user_id,
            event_id=event_id,
            evaluation=evaluation,
        )
    )
    retained = asyncio.run(
        storage.delete_expired_history(
            db, digest_date_before="2026-09-04", event_last_seen_before="2026-09-01"
        )
    )
    assert retained["events"] == 0
    row = connection.execute("SELECT * FROM jev_evaluations").fetchone()
    assert row["decision"] == "irrelevant"
    assert json.loads(row["components"])[0]["p_yes"] == 0
    assert json.loads(row["selected_event_types"]) == ["film"]
    removed = asyncio.run(
        storage.delete_expired_history(
            db, digest_date_before="2026-09-06", event_last_seen_before="2026-09-01"
        )
    )
    assert removed["events"] == 1
    assert connection.execute("SELECT COUNT(*) FROM jev_evaluations").fetchone()[0] == 0


def test_forward_jev_migration_preserves_existing_users_events_and_recommendations():
    connection = database()
    user_id, run_id = seed_user_and_run(connection)
    event_id = connection.execute(
        "INSERT INTO events(event_key,title,url,start_at,source) "
        "VALUES ('saved','Saved event','https://example.com/saved','2026-09-05','fixture')"
    ).lastrowid
    asyncio.run(
        storage.record_recommendation(
            SQLiteD1(connection),
            digest_run_id=run_id,
            user_id=user_id,
            event_id=event_id,
            position=1,
            relevance_reason="Existing choice",
            model_id="existing-model",
            used_fallback=False,
        )
    )
    # Reproduce the already deployed schema before the additive migration.
    connection.executescript("DROP TABLE jev_evaluations; DROP TABLE jev_answer_cache;")
    migration = WORKER_PATH.parent.parent / "migrations/0001_jev_evaluations.sql"
    connection.executescript(migration.read_text())
    assert connection.execute("SELECT id FROM users").fetchone()[0] == user_id
    assert connection.execute("SELECT COUNT(*) FROM digest_runs").fetchone()[0] == 1
    assert (
        connection.execute("SELECT event_id FROM recommendations").fetchone()[0]
        == event_id
    )
    assert connection.execute("SELECT title FROM events").fetchone()[0] == "Saved event"
    assert connection.execute("SELECT COUNT(*) FROM jev_evaluations").fetchone()[0] == 0
