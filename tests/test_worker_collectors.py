import asyncio
import importlib.util
import sqlite3
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

WORKER_DIR = Path(__file__).resolve().parents[1] / "cloudflare" / "worker" / "src"
sys.path.insert(0, str(WORKER_DIR))

spec = importlib.util.spec_from_file_location(
    "cloudflare_worker_collectors", WORKER_DIR / "worker_collectors.py"
)
collectors = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(collectors)


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


def fixture(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / name).read_text()


def test_parses_rss_and_atom_into_valencia_aware_events():
    rss = collectors.parse_rss(
        fixture("ajuntament_rss.xml"), "https://www.valencia.es/agenda.xml"
    )
    atom = collectors.parse_rss(
        fixture("atom_events.xml"), "https://example.com/atom.xml"
    )

    assert rss == [
        {
            "title": "Concierto en Plaza del Ayuntamiento",
            "start_at": "2025-10-13T20:00:00+02:00",
            "url": "https://www.valencia.es/eventos/concierto-plaza",
            "description": "Concierto gratuito al aire libre.",
        }
    ]
    assert atom[0]["title"] == "Atom Family Workshop"
    assert atom[0]["start_at"] == "2025-10-20T10:00:00+02:00"


def test_parses_ajuntament_embedded_events_without_scrapy():
    events = collectors.parse_ajuntament_agenda(
        fixture("ajuntament_agenda.html"),
        "https://www.valencia.es/cas/agenda-de-la-ciudad",
    )

    assert len(events) == 2
    assert events[0] == {
        "title": "Teatro familiar en el centro",
        "start_at": "2026-02-22T12:00:00+01:00",
        "end_at": "",
        "url": "https://www.valencia.es/cas/agenda-de-la-ciudad/-/content/teatro-familiar-centro",
        "description": "TEATRO. Función familiar",
    }
    assert events[1]["url"].endswith("/cas/agenda-evento/concierto-peques")
    assert events[1]["start_at"] == "2026-02-21T08:00:00+01:00"
    assert events[1]["end_at"] == ""


def test_active_ranges_include_short_runs_and_final_days_without_generic_noise():
    target = date(2026, 9, 5)
    events = [
        {
            "title": "Short festival",
            "start_at": "2026-08-28T12:00:00+02:00",
            "end_at": "2026-09-05T12:00:00+02:00",
            "url": "https://example.com/festival",
            "description": "Circus programme",
        },
        {
            "title": "Year-round listings page",
            "start_at": "2026-01-02T12:00:00+01:00",
            "end_at": "2026-12-31T12:00:00+01:00",
            "url": "https://example.com/listings",
            "description": "Generic programme",
        },
        {
            "title": "Exhibition closing tomorrow",
            "start_at": "2026-04-23T12:00:00+02:00",
            "end_at": "2026-09-05T12:00:00+02:00",
            "url": "https://example.com/exhibition",
            "description": "Final chance",
        },
    ]

    selected = [
        collectors.event_for_target(event, "fixture", target)
        for event in events
        if collectors.event_matches_date(event, target)
    ]

    assert [event["title"] for event in selected] == [
        "Short festival",
        "Exhibition closing tomorrow",
    ]
    assert all("end_at" not in event for event in selected)
    assert all("through 2026-09-05" in event["description"] for event in selected)


def test_collection_is_bounded_filtered_and_failure_isolated():
    calls = []
    feeds = {
        "https://example.com/good.xml": fixture("ajuntament_rss.xml"),
        "https://example.com/other.xml": fixture("elperiodic_valencia_rss.xml"),
    }

    async def fake_fetch(url, user_agent, timeout_ms):
        calls.append((url, user_agent, timeout_ms))
        if url.endswith("broken.xml"):
            raise RuntimeError("http_503")
        return feeds[url]

    sources = (
        collectors.Source("good", "https://example.com/good.xml", collectors.parse_rss),
        collectors.Source(
            "broken", "https://example.com/broken.xml", collectors.parse_rss
        ),
        collectors.Source(
            "other", "https://example.com/other.xml", collectors.parse_rss
        ),
    )

    events, diagnostics = asyncio.run(
        collectors.collect_events(
            SimpleNamespace(EVENT_FETCH=fake_fetch),
            date(2025, 10, 13),
            sources,
        )
    )

    assert [event["source"] for event in events] == ["good"]
    assert diagnostics == [
        {"source": "good", "status": "ok", "parsed": 1, "matched": 1},
        {"source": "broken", "status": "failed", "error_code": "http_503"},
        {"source": "other", "status": "ok", "parsed": 1, "matched": 0},
    ]
    assert len(calls) == 3
    assert all(call[1] == collectors.USER_AGENT for call in calls)
    assert all(call[2] == 10_000 for call in calls)


def test_persist_events_deduplicates_in_d1():
    connection = sqlite3.connect(":memory:")
    connection.executescript((WORKER_DIR / "schema.sql").read_text())
    db = SQLiteD1(connection)
    event = {
        "title": "Tomorrow at the museum",
        "start_at": "2026-09-05T12:00:00+02:00",
        "url": "https://example.com/museum",
        "description": "A family exhibition.",
        "source": "fixture",
    }

    unique = asyncio.run(collectors.persist_events(db, [event, event]))

    assert unique == 1
    assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
