import asyncio
import importlib.util
import json
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


def test_dry_run_reports_only_aggregate_fallback_reasons():
    connection = database(user_count=1)

    async def fallback_ranker(env, preferences_blob, ranked_events):
        del env, preferences_blob
        return ranking_module.Ranking(
            [
                {
                    **ranked_events[0],
                    "relevance_reason": "A deterministic fallback selection.",
                }
            ],
            "deterministic",
            True,
            "missing_json_object",
        )

    summary = asyncio.run(
        orchestrator.run_digest(
            SimpleNamespace(
                DB=SQLiteD1(connection),
                COLLECT_EVENTS=fake_collector,
                RANK_EVENTS=fallback_ranker,
                EMAIL_FROM="Brisa <hello@example.com>",
                APP_BASE_URL="https://events.example.com",
            ),
            now=datetime(2026, 9, 4, 8, tzinfo=UTC),
            dry_run=True,
        )
    )

    assert summary["fallback_count"] == 1
    assert summary["fallback_reasons"] == {"missing_json_object": 1}
    assert "reader-0@example.com" not in json.dumps(summary)


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


def test_offline_pipeline_collects_ranks_delivers_and_replays_safely():
    connection = database(user_count=0)
    fixture = Path(__file__).parent / "fixtures" / "full_pipeline_events.xml"

    def profile(interest: str) -> str:
        return json.dumps(
            {
                "audience": "adults",
                "location_scope": "València",
                "top_interest_clusters": [interest],
                "strong_positive_signals": [interest],
                "strong_negative_signals": [],
                "seasonal_anchors": ["autumn"],
            }
        )

    users: dict[str, int] = {}
    for name, interest, active in (
        ("art", "art", 1),
        ("music", "music", 1),
        ("fallback", "provider-failure", 1),
        ("paused", "art", 1),
        ("pending", "music", 0),
    ):
        cursor = connection.execute(
            "INSERT INTO users (email, preferences_blob, is_active) VALUES (?, ?, ?)",
            (f"{name}@example.com", profile(interest), active),
        )
        users[name] = int(cursor.lastrowid)
    connection.execute(
        "INSERT INTO subscriptions (user_id, is_subscribed) VALUES (?, 0)",
        (users["paused"],),
    )
    connection.commit()

    provider_profiles: list[dict] = []
    delivery_attempts: dict[str, int] = {}
    delivered: list[tuple[str, dict[str, str]]] = []

    async def fixture_fetch(url, user_agent, timeout_ms):
        assert user_agent.startswith("BrisaEventDigest/")
        assert timeout_ms == 10_000
        if "elperiodic.com" in url:
            return fixture.read_text()
        raise RuntimeError("fixture_unavailable")

    async def openrouter_fetch(body):
        request = json.loads(body["messages"][1]["content"])
        request_profile = request["profile"]
        provider_profiles.append(request_profile)
        interest = request_profile["top_interest_clusters"][0]
        if interest == "provider-failure":
            raise RuntimeError("http_503")
        candidates = request["events"]
        preferred = "concert" if interest == "music" else "art"
        ordered = sorted(
            candidates,
            key=lambda event: preferred not in event["title"].casefold(),
        )
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "recommendations": [
                                    {
                                        "event_key": event["event_key"],
                                        "reason": f"A strong {interest} match.",
                                    }
                                    for event in ordered
                                ]
                            }
                        )
                    }
                }
            ]
        }

    async def mailgun_delivery(recipient, message):
        delivery_attempts[recipient] = delivery_attempts.get(recipient, 0) + 1
        if recipient == "fallback@example.com" and delivery_attempts[recipient] == 1:
            raise RuntimeError("mailgun_http_503")
        delivered.append((recipient, message))
        return f"provider-{recipient}-{delivery_attempts[recipient]}"

    runtime_env = SimpleNamespace(
        DB=SQLiteD1(connection),
        EVENT_FETCH=fixture_fetch,
        OPENROUTER_FETCH=openrouter_fetch,
        DIGEST_DELIVERY=mailgun_delivery,
        EMAIL_FROM="Brisa <hello@example.com>",
        APP_BASE_URL="https://events.example.com",
    )
    now = datetime(2025, 10, 12, 8, tzinfo=UTC)

    first = asyncio.run(orchestrator.run_digest(runtime_env, now=now, dry_run=False))

    assert first["event_count"] == 2
    assert first["subscriber_count"] == 3
    assert first["sent_count"] == 2
    assert first["failure_count"] == 1
    assert first["fallback_count"] == 1
    assert first["fallback_reasons"] == {"http_503": 1}
    assert {recipient for recipient, _message in delivered} == {
        "art@example.com",
        "music@example.com",
    }
    assert all("Brisa picks" in message["subject"] for _recipient, message in delivered)
    assert all(
        "@example.com" not in json.dumps(request_profile)
        for request_profile in provider_profiles
    )

    first_choices = connection.execute(
        """
        SELECT users.email, events.title, recommendations.position,
               recommendations.model_id, recommendations.used_fallback
        FROM recommendations
        JOIN users ON users.id = recommendations.user_id
        JOIN events ON events.id = recommendations.event_id
        ORDER BY users.email, recommendations.position
        """
    ).fetchall()
    choices = {
        email: [
            (title, model_id, used_fallback)
            for row_email, title, _, model_id, used_fallback in first_choices
            if row_email == email
        ]
        for email in {row[0] for row in first_choices}
    }
    assert choices["art@example.com"][0][0] == "Morning art workshop"
    assert choices["music@example.com"][0][0] == "Evening chamber concert"
    assert choices["fallback@example.com"][0][1:] == ("deterministic", 1)
    assert connection.execute("SELECT COUNT(*) FROM digest_runs").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 2
    assert connection.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0] == 6

    connection.execute(
        "UPDATE deliveries SET updated_at = datetime('now', '-6 minutes') "
        "WHERE status = 'failed'"
    )
    connection.commit()
    replay = asyncio.run(orchestrator.run_digest(runtime_env, now=now, dry_run=False))

    assert replay["sent_count"] == 1
    assert replay["skipped_count"] == 2
    assert replay["failure_count"] == 0
    assert delivery_attempts == {
        "art@example.com": 1,
        "music@example.com": 1,
        "fallback@example.com": 2,
    }
    deliveries = connection.execute(
        "SELECT status, attempt_count FROM deliveries ORDER BY user_id"
    ).fetchall()
    assert [tuple(row) for row in deliveries] == [
        ("sent", 1),
        ("sent", 1),
        ("sent", 2),
    ]


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
