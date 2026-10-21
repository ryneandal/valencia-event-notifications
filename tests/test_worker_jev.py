import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cloudflare" / "worker" / "src"))

import worker_jev as jev  # noqa: E402
from worker_preferences import EVENT_TYPE_INCLUDES  # noqa: E402


def event(**changes):
    return {
        "event_key": "event-one",
        "title": "Jazz in the garden",
        "description": "A jazz quartet plays outdoors.",
        "url": "https://example.com/jazz",
        **changes,
    }


def response(body, value=0.9):
    return {
        "model": body["model"],
        "answers": {key: {"type": "noul", "noul": value} for key in body["questions"]},
        "usage": {"input_tokens": 12, "output_tokens": 4},
    }


def runtime(fetch, **changes):
    return SimpleNamespace(JEV_MODE="shadow", JEV_FETCH=fetch, **changes)


def test_every_catalog_type_has_one_reviewed_independent_question():
    expected = json.loads((ROOT / "cloudflare/shared/jev-questions.json").read_text())
    questions = jev.build_questions(list(EVENT_TYPE_INCLUDES))
    assert len(questions) == 12
    assert questions == expected["questions"]
    assert expected["version"] == jev.QUESTION_VERSION
    assert expected["taxonomy_version"] == jev.TAXONOMY_VERSION
    for question in questions.values():
        assert question["type"] == "noul"
        assert question["instructions"].endswith("?")
        assert "relevan" not in question["instructions"].lower()
        assert set(question["criteria"]) == {"true", "false"}


@pytest.mark.parametrize("selected", [[], ["film", "film"], ["unknown"], [None]])
def test_build_questions_rejects_unbounded_selections(selected):
    with pytest.raises(ValueError, match="invalid_preferences"):
        jev.build_questions(selected)


def test_request_whitelists_and_bounds_canonical_event_evidence():
    body = jev.build_request(
        event(
            description="x" * 20_000,
            title="Title" * 500,
            venue="v" * 1000,
            category="c" * 1000,
            start_at="s" * 1000,
            timezone="z" * 1000,
            source="r" * 1000,
            source_url="https://private.example.com/feed?token=fake-private-key",
            email="private@example.com",
            preferences_blob="private profile",
            session="private-session",
            api_key="fake-private-key",
        ),
        jev.build_questions(["live_music", "food_drink"]),
        jev.DEFAULT_MODEL,
    )
    evidence = body["state"]["event"]
    assert {key: len(value) for key, value in evidence.items()} == {
        "title": 500,
        "description": 8000,
        "start_at": 64,
        "timezone": 64,
        "source": 200,
        "venue": 500,
        "category": 500,
    }
    assert "private" not in json.dumps(body)
    assert "event_key" not in json.dumps(body)
    assert "url" not in evidence
    assert len(body["questions"]) == 2


def test_request_includes_canonical_start_explicit_timezone_and_source():
    request = jev.build_request(
        event(
            start_at="2026-10-22T18:00:00+02:00",
            timezone="Europe/Madrid",
            source="venue-rss",
        ),
        jev.build_questions(["live_music"]),
        jev.DEFAULT_MODEL,
    )
    evidence = request["state"]["event"]
    assert evidence["start_at"] == "2026-10-22T18:00:00+02:00"
    assert evidence["timezone"] == "Europe/Madrid"
    assert evidence["source"] == "venue-rss"


@pytest.mark.parametrize(
    "start_at,timezone",
    [
        ("2026-10-22T18:00:00+02:00", "UTC+02:00"),
        ("2026-12-22T18:00:00+01:00", "UTC+01:00"),
        ("2026-10-22T16:00:00Z", "UTC"),
    ],
)
def test_request_derives_timezone_from_aware_start_when_zone_is_absent(
    start_at, timezone
):
    request = jev.build_request(
        event(start_at=start_at, source="venue-rss"),
        jev.build_questions(["live_music"]),
        jev.DEFAULT_MODEL,
    )
    assert request["state"]["event"]["timezone"] == timezone


@pytest.mark.parametrize("start_at", [None, "invalid start", "2026-10-22T18:00:00"])
def test_request_does_not_invent_timezone_without_an_explicit_zone_or_offset(start_at):
    request = jev.build_request(
        event(start_at=start_at), jev.build_questions(["film"]), jev.DEFAULT_MODEL
    )
    assert "timezone" not in request["state"]["event"]


def test_request_rejects_arbitrary_questions_and_model_aliases():
    questions = jev.build_questions(["film"])
    with pytest.raises(ValueError, match="invalid_model"):
        jev.build_request(event(), questions, "jev-latest")
    questions["event_type:film"]["instructions"] = "Is this relevant to Alice?"
    with pytest.raises(ValueError, match="invalid_questions"):
        jev.build_request(event(), questions, jev.DEFAULT_MODEL)


@pytest.mark.parametrize(
    "name", ["matched", "irrelevant", "uncertain", "threshold_equality"]
)
def test_transport_and_scoring_match_shared_examples(name):
    examples = json.loads(
        (ROOT / "cloudflare/shared/jev-preview.examples.json").read_text()
    )
    expected = examples[name]

    async def fake(body):
        assert set(body["questions"]) == {
            c["question_id"] for c in expected["components"]
        }
        return {
            "model": expected["model"],
            "answers": {
                c["question_id"]: {"type": "noul", "noul": c["p_yes"]}
                for c in expected["components"]
            },
        }

    result = asyncio.run(
        jev.evaluate_event(
            runtime(fake), expected["event"], expected["selected_event_types"]
        )
    )
    assert result["evaluated_at"].endswith("Z")
    result["evaluated_at"] = expected["evaluated_at"]
    assert result == expected


@pytest.mark.parametrize("mode", [None, "off", "misspelled"])
def test_off_mode_never_calls_provider(mode):
    async def forbidden(_body):
        pytest.fail("off mode attempted a provider call")

    env = SimpleNamespace(JEV_FETCH=forbidden)
    if mode is not None:
        env.JEV_MODE = mode
    result = asyncio.run(jev.evaluate_event(env, event(), ["film"]))
    assert result["error_code"] == "feature_disabled"


def test_invalid_preferences_do_not_send_questions():
    async def forbidden(_body):
        pytest.fail("invalid preferences attempted a provider call")

    result = asyncio.run(jev.evaluate_event(runtime(forbidden), event(), ["unknown"]))
    assert result["error_code"] == "invalid_preferences"
    assert result["selected_event_types"] == []


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        [],
        {"model": "unexpected", "answers": {}},
        {"model": jev.DEFAULT_MODEL, "answers": {}},
        {
            "model": jev.DEFAULT_MODEL,
            "answers": {"event_type:film": {"type": "noul", "noul": True}},
        },
    ],
)
def test_malformed_responses_are_not_retried_or_treated_as_exclusions(invalid):
    calls = 0

    async def fake(_body):
        nonlocal calls
        calls += 1
        return invalid

    result = asyncio.run(jev.evaluate_event(runtime(fake), event(), ["film"]))
    assert result["error_code"] == "invalid_provider_response"
    assert result["decision"] == "unknown"
    assert calls == 1


def test_connection_failure_retries_once_without_leaking_exception(monkeypatch, capsys):
    monkeypatch.setattr(jev, "RETRY_DELAY_SECONDS", 0)
    calls = 0

    async def fake(_body):
        nonlocal calls
        calls += 1
        raise RuntimeError("Bearer fake-sensitive-token private@example.com")

    result = asyncio.run(jev.evaluate_event(runtime(fake), event(), ["film"]))
    assert calls == 2
    assert result["error_code"] == "provider_unavailable"
    assert "sensitive" not in json.dumps(result) + capsys.readouterr().out


@pytest.mark.parametrize(
    "status,expected_calls", [(401, 1), (422, 1), (429, 2), (529, 2), (503, 2)]
)
def test_http_retry_policy(monkeypatch, status, expected_calls):
    monkeypatch.setattr(jev, "RETRY_DELAY_SECONDS", 0)
    calls = 0

    async def fake(body):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise jev.ProviderHTTPError(status, retry_after=0)
        return response(body)

    result = asyncio.run(jev.evaluate_event(runtime(fake), event(), ["film"]))
    assert calls == expected_calls
    assert result["status"] == ("evaluated" if expected_calls == 2 else "fallback")


def test_retry_after_beyond_remaining_budget_does_not_wait_or_retry():
    calls = 0

    async def fake(_body):
        nonlocal calls
        calls += 1
        raise jev.ProviderHTTPError(429, retry_after=3600)

    result = asyncio.run(jev.evaluate_event(runtime(fake), event(), ["film"]))
    assert calls == 1
    assert result["status"] == "fallback"


def test_attempt_timeouts_cancel_and_retry_only_once(monkeypatch):
    monkeypatch.setattr(jev, "ATTEMPT_TIMEOUT_SECONDS", 0.001)
    monkeypatch.setattr(jev, "RETRY_DELAY_SECONDS", 0)
    calls = 0
    cancelled = 0

    async def fake(_body):
        nonlocal calls, cancelled
        calls += 1
        try:
            await asyncio.sleep(10)
        finally:
            cancelled += 1

    result = asyncio.run(jev.evaluate_event(runtime(fake), event(), ["film"]))
    assert calls == cancelled == 2
    assert result["status"] == "fallback"


def test_batch_has_two_concurrent_calls_and_a_single_whole_batch_budget(monkeypatch):
    monkeypatch.setattr(jev, "EVALUATION_BUDGET_SECONDS", 0.02)
    calls = 0
    active = 0
    peak = 0

    async def fake(_body):
        nonlocal calls, active, peak
        calls += 1
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(10)
        finally:
            active -= 1

    results = asyncio.run(
        jev.evaluate_events(
            runtime(fake), [event(event_key=f"event-{i}") for i in range(5)], ["film"]
        )
    )
    assert peak == calls == 2
    assert active == 0
    assert len(results) == 5
    assert all(item["error_code"] == "budget_exhausted" for item in results)


def test_cache_key_depends_on_evidence_versions_and_model_only(
    monkeypatch,
):
    def key(e, selected=None, model=jev.DEFAULT_MODEL):
        return jev.cache_key(
            jev.build_request(e, jev.build_questions(selected or ["film"]), model)
        )

    original = key(event())
    assert (
        key(event(email="other@example.com", preferences_blob="other"), ["live_music"])
        == original
    )
    assert key(event(description="changed text")) != original
    assert key(event(), model="jev-1.14.0") != original
    monkeypatch.setattr(jev, "QUESTION_VERSION", "event-type-questions-v2")
    assert key(event()) != original


@pytest.mark.parametrize(
    "changed",
    [
        {"start_at": "2026-10-22T19:00:00+02:00"},
        {"timezone": "Europe/Paris"},
        {"source": "updated-venue-rss"},
    ],
)
def test_canonical_time_timezone_and_source_changes_invalidate_cached_answers(changed):
    canonical = event(
        start_at="2026-10-22T18:00:00+02:00",
        timezone="Europe/Madrid",
        source="venue-rss",
    )
    questions = jev.build_questions(["live_music"])
    original = jev.cache_key(jev.build_request(canonical, questions, jev.DEFAULT_MODEL))
    updated = jev.cache_key(
        jev.build_request({**canonical, **changed}, questions, jev.DEFAULT_MODEL)
    )
    assert updated != original


def test_saved_profile_extracts_only_supported_unique_names():
    assert jev.selected_types(
        json.dumps(
            {
                "top_interest_clusters": [
                    {"name": "film", "includes": ["arbitrary private text"]}
                ]
            }
        )
    ) == ["film"]
    for value in (
        None,
        "not json",
        "[]",
        '{"top_interest_clusters": [{}]}',
        '{"top_interest_clusters": [{"name": "film"}, {"name": "film"}]}',
    ):
        assert jev.selected_types(value) == []


def test_native_worker_fetch_uses_auth_bounded_timeout_and_json_body(monkeypatch):
    captured = []

    class AbortSignal:
        @staticmethod
        def timeout(milliseconds):
            assert 0 < milliseconds <= 5000
            return "fake-abort-signal"

    class FakeResponse:
        status = 200

        def __init__(self, body):
            self.body = body

        async def json(self):
            return response(self.body)

    async def fake_fetch(url, options):
        captured.append((url, options))
        return FakeResponse(json.loads(options["body"]))

    converter = object()
    js = SimpleNamespace(
        AbortSignal=AbortSignal,
        Object=SimpleNamespace(fromEntries=converter),
        fetch=fake_fetch,
    )
    ffi = SimpleNamespace(to_js=lambda value, **_kwargs: value)
    monkeypatch.setitem(sys.modules, "js", js)
    monkeypatch.setitem(sys.modules, "pyodide", SimpleNamespace(ffi=ffi))
    monkeypatch.setitem(sys.modules, "pyodide.ffi", ffi)
    result = asyncio.run(
        jev.evaluate_event(
            SimpleNamespace(JEV_MODE="shadow", TYPESAFE_API_KEY="fake-test-key"),
            event(),
            ["live_music"],
        )
    )
    assert result["status"] == "evaluated"
    url, options = captured[0]
    assert url == "https://api.typesafe.ai/v1/systemone"
    assert options["method"] == "POST"
    assert options["headers"] == {
        "authorization": "Bearer fake-test-key",
        "content-type": "application/json",
    }
    assert options["signal"] == "fake-abort-signal"
    assert "fake-test-key" not in options["body"] + json.dumps(result)


def test_http_error_never_reads_raw_provider_error_body():
    class UnauthorizedResponse:
        status = 401
        headers = {}

        async def json(self):
            pytest.fail("Raw error body must not be read")

    async def fake(_body):
        return UnauthorizedResponse()

    result = asyncio.run(jev.evaluate_event(runtime(fake), event(), ["film"]))
    assert result["error_code"] == "provider_unavailable"


def test_retry_after_headers_are_honored_within_budget(monkeypatch):
    delays = []
    calls = 0

    class RateLimitResponse:
        status = 429
        headers = {"retry-after-ms": "600"}

    async def fake(body):
        nonlocal calls
        calls += 1
        return RateLimitResponse() if calls == 1 else response(body)

    async def fake_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(jev.asyncio, "sleep", fake_sleep)
    result = asyncio.run(jev.evaluate_event(runtime(fake), event(), ["film"]))
    assert result["status"] == "evaluated"
    assert calls == 2
    assert delays == [0.6]
