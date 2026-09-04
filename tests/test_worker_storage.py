import asyncio
import importlib.util
import sqlite3
import sys
from pathlib import Path

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
    assert asyncio.run(storage.claim_delivery(db, run_id, user_id)) is True

    delivery = connection.execute(
        "SELECT status, attempt_count, last_error_code FROM deliveries"
    ).fetchone()
    assert tuple(delivery) == ("pending", 2, None)


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
