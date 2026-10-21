import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

WORKER_DIR = Path(__file__).resolve().parents[1] / "cloudflare" / "worker" / "src"
sys.path.insert(0, str(WORKER_DIR))

spec = importlib.util.spec_from_file_location(
    "cloudflare_worker_ranking", WORKER_DIR / "worker_ranking.py"
)
ranking = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ranking)


def profile_blob() -> str:
    return json.dumps(
        {
            "audience": "family_with_school_age_kids",
            "location_scope": ["Valencia city"],
            "top_interest_clusters": [
                {"name": "arts", "includes": ["museums", "workshops"]}
            ],
            "strong_positive_signals": ["near_transit"],
            "strong_negative_signals": ["starts_after_20"],
            "seasonal_anchors": [{"name": "Fallas", "months": [3]}],
        }
    )


def events() -> list[dict]:
    return [
        {
            "id": 99,
            "event_key": "event-later",
            "title": "Late concert",
            "start_at": "2026-09-05T20:00:00+02:00",
            "url": "https://example.com/later",
            "description": "Music",
            "source": "fixture",
        },
        {
            "id": 42,
            "event_key": "event-first",
            "title": "Morning museum",
            "start_at": "2026-09-05T10:00:00+02:00",
            "url": "https://example.com/first",
            "description": "Art",
            "source": "fixture",
        },
    ]


def test_openrouter_ranking_uses_default_model_and_privacy_bounded_payload():
    captured = []

    async def fake_fetch(body):
        captured.append(body)
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '```json\n{"recommendations":['
                            '{"event_key":"event-first","reason":"Great art fit"},'
                            '{"event_key":"event-later","reason":"Live music option"}'
                            "]}\n```"
                        )
                    }
                }
            ]
        }

    result = asyncio.run(
        ranking.rank_events(
            SimpleNamespace(OPENROUTER_FETCH=fake_fetch), profile_blob(), events()
        )
    )

    assert result.model_id == ranking.DEFAULT_MODEL
    assert result.used_fallback is False
    assert [event["event_key"] for event in result.events] == [
        "event-first",
        "event-later",
    ]
    assert result.events[0]["relevance_reason"] == "Great art fit"
    request = captured[0]
    assert request["model"] == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert request["response_format"] == {"type": "json_object"}
    assert request["plugins"] == [{"id": "response-healing"}]
    assert "provider" not in request
    request_text = json.dumps(request)
    assert "reader@example.com" not in request_text
    assert '"id": 99' not in request_text
    assert set(json.loads(request["messages"][1]["content"])["profile"]) == set(
        ranking.PROFILE_FIELDS
    )


def test_malformed_or_unknown_provider_output_uses_deterministic_fallback():
    responses = [
        {"choices": [{"message": {"content": "not json"}}]},
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"recommendations":['
                            '{"event_key":"unknown","reason":"Nope"}]}'
                        )
                    }
                }
            ]
        },
    ]

    for response in responses:

        async def fake_fetch(body, response=response):
            del body
            return response

        result = asyncio.run(
            ranking.rank_events(
                SimpleNamespace(OPENROUTER_FETCH=fake_fetch),
                profile_blob(),
                events(),
            )
        )
        assert result.used_fallback is True
        assert result.model_id == "deterministic"
        assert [event["event_key"] for event in result.events] == [
            "event-first",
            "event-later",
        ]
        assert result.error_code


def test_malformed_provider_output_is_retried_once_before_fallback():
    responses = [
        {"choices": [{"message": {"content": "not json"}}]},
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"recommendations":['
                            '{"event_key":"event-first","reason":"Recovered art fit"}'
                            "]}"
                        )
                    }
                }
            ]
        },
    ]
    calls = 0

    async def flaky_fetch(body):
        nonlocal calls
        del body
        response = responses[calls]
        calls += 1
        return response

    result = asyncio.run(
        ranking.rank_events(
            SimpleNamespace(OPENROUTER_FETCH=flaky_fetch), profile_blob(), events()
        )
    )

    assert calls == 2
    assert result.used_fallback is False
    assert result.model_id == ranking.DEFAULT_MODEL
    assert result.events[0]["relevance_reason"] == "Recovered art fit"


def test_missing_key_provider_failure_and_invalid_profile_fail_safe():
    provider_calls = 0
    missing_key = asyncio.run(
        ranking.rank_events(SimpleNamespace(), profile_blob(), events())
    )

    async def failed_fetch(body):
        nonlocal provider_calls
        del body
        provider_calls += 1
        raise RuntimeError("http_429")

    provider_failure = asyncio.run(
        ranking.rank_events(
            SimpleNamespace(OPENROUTER_FETCH=failed_fetch), profile_blob(), events()
        )
    )
    invalid_profile = asyncio.run(
        ranking.rank_events(SimpleNamespace(), "{}", events())
    )

    assert missing_key.error_code == "missing_api_key"
    assert provider_failure.error_code == "http_429"
    assert provider_calls == 1
    assert invalid_profile.error_code == "incomplete_profile"
    assert all(
        result.used_fallback
        for result in (missing_key, provider_failure, invalid_profile)
    )


def supported_profile() -> str:
    profile = json.loads(profile_blob())
    profile["top_interest_clusters"] = [
        {"name": "live_music", "includes": ["concerts"]}
    ]
    return json.dumps(profile)


def test_jev_filter_preserves_other_preferences_and_cannot_resurrect_rejected_events():
    captured = []

    async def jev(body):
        is_music = "concert" in body["state"]["event"]["title"].lower()
        return {
            "model": body["model"],
            "answers": {
                "event_type:live_music": {
                    "type": "noul",
                    "noul": 0.9 if is_music else 0.05,
                }
            },
        }

    async def invalid_ranking(body):
        captured.append(json.loads(body["messages"][1]["content"]))
        # Even a provider response naming a previously rejected event is invalid.
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"recommendations":[{"event_key":"event-first",'
                            '"reason":"Bring it back"}]}'
                        )
                    }
                }
            ]
        }

    result = asyncio.run(
        ranking.rank_events(
            SimpleNamespace(
                JEV_MODE="filter", JEV_FETCH=jev, OPENROUTER_FETCH=invalid_ranking
            ),
            supported_profile(),
            events(),
        )
    )
    assert result.used_fallback is True
    assert [e["event_key"] for e in result.events] == ["event-later"]
    assert len(result.evaluations) == 2
    assert result.evaluations[1]["decision"] == "irrelevant"
    assert all(len(body["events"]) == 1 for body in captured)
    assert captured[0]["profile"] == json.loads(supported_profile())


def test_all_rejected_is_a_successful_empty_ranking_without_openrouter_call():
    async def jev(body):
        return {
            "model": body["model"],
            "answers": {"event_type:live_music": {"type": "noul", "noul": 0.05}},
        }

    async def forbidden(_body):
        raise AssertionError("Empty candidate list must not reach OpenRouter")

    result = asyncio.run(
        ranking.rank_events(
            SimpleNamespace(
                JEV_MODE="filter", JEV_FETCH=jev, OPENROUTER_FETCH=forbidden
            ),
            supported_profile(),
            events(),
        )
    )
    assert result.events == []
    assert result.used_fallback is False
    assert len(result.evaluations) == 2


def test_shadow_and_uncertainty_keep_existing_candidate_fallback():
    for mode, probability in (("shadow", 0.0), ("filter", 0.5)):

        async def jev(body, probability=probability):
            return {
                "model": body["model"],
                "answers": {
                    "event_type:live_music": {"type": "noul", "noul": probability}
                },
            }

        result = asyncio.run(
            ranking.rank_events(
                SimpleNamespace(JEV_MODE=mode, JEV_FETCH=jev),
                supported_profile(),
                events(),
            )
        )
        assert result.used_fallback is True  # OpenRouter key is deliberately absent.
        assert len(result.events) == 2
        assert len(result.evaluations) == 2


def test_off_makes_no_jev_calls_and_invalid_preferences_cannot_filter():
    async def forbidden(_body):
        raise AssertionError("Must not call Jev")

    result = asyncio.run(
        ranking.rank_events(
            SimpleNamespace(JEV_MODE="off", JEV_FETCH=forbidden),
            supported_profile(),
            events(),
        )
    )
    assert len(result.events) == 2
    assert result.evaluations == []
    result = asyncio.run(
        ranking.rank_events(
            SimpleNamespace(JEV_MODE="filter", JEV_FETCH=forbidden),
            profile_blob(),
            events(),  # The legacy 'arts' ID is unsupported.
        )
    )
    assert len(result.events) == 2
    assert all(e["error_code"] == "invalid_preferences" for e in result.evaluations)
