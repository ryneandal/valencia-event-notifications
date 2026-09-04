import asyncio
import importlib.util
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

WORKER_DIR = Path(__file__).resolve().parents[1] / "cloudflare" / "worker" / "src"
sys.path.insert(0, str(WORKER_DIR))


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, WORKER_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


orchestrator = load_module("worker_orchestrator")
ranking_module = load_module("worker_ranking")


class SQLiteD1:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def prepare(self, sql: str):
        return SQLiteStatement(self.connection, sql)


class SQLiteStatement:
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
        return {"success": True, "meta": {"changes": max(cursor.rowcount, 0)}}

    async def first(self):
        row = self.connection.execute(self.sql, self.params).fetchone()
        return dict(row) if row is not None else None

    async def all(self):
        rows = self.connection.execute(self.sql, self.params).fetchall()
        return {"success": True, "results": [dict(row) for row in rows]}


def database(user_count: int = 2) -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript((WORKER_DIR / "schema.sql").read_text())
    for index in range(user_count):
        connection.execute(
            """
            INSERT INTO users (email, preferences_blob, is_active)
            VALUES (?, ?, 1)
            """,
            (f"reader-{index}@example.com", '{"profile":"fixture"}'),
        )
    connection.commit()
    return connection


async def fake_collector(env, target_date):
    del env
    original_start = target_date - timedelta(days=2)
    return (
        [
            {
                "title": "An exhibition continuing tomorrow",
                "start_at": f"{original_start.isoformat()}T11:00:00+02:00",
                "url": "https://example.com/ivam",
                "description": "A family exhibition active through tomorrow.",
                "source": "fixture",
            }
        ],
        [{"source": "fixture", "status": "ok", "parsed": 1, "matched": 1}],
    )


async def fake_ranker(env, preferences_blob, events):
    del env, preferences_blob
    return ranking_module.Ranking(
        [{**events[0], "relevance_reason": "A good family art match."}],
        "fixture-model",
        False,
    )


def test_dry_run_renders_every_user_without_calling_delivery():
    connection = database()

    async def forbidden_delivery(recipient, message):
        raise AssertionError(f"dry run attempted delivery to {recipient}: {message}")

    summary = asyncio.run(
        orchestrator.run_digest(
            SimpleNamespace(
                DB=SQLiteD1(connection),
                COLLECT_EVENTS=fake_collector,
                RANK_EVENTS=fake_ranker,
                DIGEST_DELIVERY=forbidden_delivery,
                EMAIL_FROM="Brisa <hello@example.com>",
                APP_BASE_URL="https://events.example.com",
            ),
            now=datetime(2026, 9, 4, 8, tzinfo=UTC),
            dry_run=True,
        )
    )

    assert summary["event_count"] == 1
    assert summary["subscriber_count"] == 2
    assert summary["rendered_count"] == 2
    assert summary["sent_count"] == 0
    assert summary["failure_count"] == 0
    assert connection.execute("SELECT COUNT(*) FROM digest_runs").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0] == 2
    assert connection.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0] == 0


def test_live_retry_isolates_failure_and_never_resends_success(capsys):
    connection = database()
    calls: list[str] = []
    failures_remaining = {"reader-0@example.com": 1}

    async def flaky_delivery(recipient, message):
        del message
        calls.append(recipient)
        if failures_remaining.get(recipient, 0):
            failures_remaining[recipient] -= 1
            raise RuntimeError("mailgun_http_503")
        return f"provider-{len(calls)}"

    runtime_env = SimpleNamespace(
        DB=SQLiteD1(connection),
        COLLECT_EVENTS=fake_collector,
        RANK_EVENTS=fake_ranker,
        DIGEST_DELIVERY=flaky_delivery,
        EMAIL_FROM="Brisa <hello@example.com>",
        APP_BASE_URL="https://events.example.com",
    )
    now = datetime(2026, 9, 4, 8, tzinfo=UTC)

    first = asyncio.run(orchestrator.run_digest(runtime_env, now=now, dry_run=False))
    connection.execute(
        "UPDATE deliveries SET updated_at = datetime('now', '-6 minutes') "
        "WHERE status = 'failed'"
    )
    connection.commit()
    second = asyncio.run(orchestrator.run_digest(runtime_env, now=now, dry_run=False))

    assert (first["sent_count"], first["failure_count"]) == (1, 1)
    assert (second["sent_count"], second["failure_count"]) == (1, 0)
    assert second["skipped_count"] == 1
    assert calls.count("reader-0@example.com") == 2
    assert calls.count("reader-1@example.com") == 1
    deliveries = connection.execute(
        "SELECT status, attempt_count FROM deliveries ORDER BY user_id"
    ).fetchall()
    assert [tuple(row) for row in deliveries] == [("sent", 2), ("sent", 1)]
    logs = capsys.readouterr().out
    assert "reader-0@example.com" not in logs
    assert '"profile":"fixture"' not in logs
    assert '"event.name": "digest.subscriber.failed"' in logs


def test_empty_run_completes_without_ranking_or_delivery():
    connection = database(user_count=0)

    async def empty_collector(env, target_date):
        del env, target_date
        return [], [{"source": "fixture", "status": "ok", "parsed": 0, "matched": 0}]

    async def forbidden_ranker(env, preferences_blob, events):
        raise AssertionError((env, preferences_blob, events))

    summary = asyncio.run(
        orchestrator.run_digest(
            SimpleNamespace(
                DB=SQLiteD1(connection),
                COLLECT_EVENTS=empty_collector,
                RANK_EVENTS=forbidden_ranker,
            ),
            now=datetime(2026, 9, 4, 8, tzinfo=UTC),
            dry_run=False,
        )
    )

    assert summary["event_count"] == 0
    assert summary["subscriber_count"] == 0
    assert summary["sent_count"] == 0
    status = connection.execute("SELECT status FROM digest_runs").fetchone()[0]
    assert status == "completed"
