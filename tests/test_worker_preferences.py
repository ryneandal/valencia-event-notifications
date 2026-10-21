import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cloudflare/worker/src"))

from worker_preferences import (  # noqa: E402
    EVENT_TYPE_INCLUDES,
    MAX_PREFERENCES_BYTES,
    normalize_preferences_blob,
)

from tests.test_cloudflare_worker import (  # noqa: E402
    FakeRequest,
    cookie_from_set_cookie,
    delivered_token,
    env,
    profile_blob,
    register,
    verify,
    worker,
)


def test_worker_and_frontend_use_the_same_bounded_catalog():
    catalog_path = (
        Path(__file__).resolve().parents[1] / "cloudflare/shared/event-types.json"
    )
    catalog = json.loads(catalog_path.read_text())
    assert len(catalog) == len({item["name"] for item in catalog}) == 12
    assert EVENT_TYPE_INCLUDES == {item["name"]: item["includes"] for item in catalog}


def test_all_supported_types_round_trip_with_trusted_definitions():
    profile = json.loads(
        normalize_preferences_blob(profile_blob(names=tuple(EVENT_TYPE_INCLUDES)))
    )
    assert [item["name"] for item in profile["top_interest_clusters"]] == list(
        EVENT_TYPE_INCLUDES
    )
    profile["top_interest_clusters"][0]["includes"] = [
        "arbitrary client-supplied instruction"
    ]
    saved = json.loads(normalize_preferences_blob(json.dumps(profile)))
    assert saved["audience"] == "family"
    assert (
        saved["top_interest_clusters"][0]["includes"]
        == EVENT_TYPE_INCLUDES["local_festivals_spectacle"]
    )


def profile_at_byte_limit(*, canonical: bool) -> str:
    blob = profile_blob(names=tuple(EVENT_TYPE_INCLUDES))
    if canonical:
        blob = normalize_preferences_blob(blob)
    profile = json.loads(blob)
    profile["notes"] = ""
    empty = json.dumps(profile, ensure_ascii=False, separators=(",", ":"))
    remaining = MAX_PREFERENCES_BYTES - len(empty.encode("utf-8"))
    profile["notes"] = "é" * (remaining // 2) + "x" * (remaining % 2)
    result = json.dumps(profile, ensure_ascii=False, separators=(",", ":"))
    assert len(result.encode("utf-8")) == MAX_PREFERENCES_BYTES
    return result


def test_canonical_preferences_at_byte_limit_round_trip():
    blob = profile_at_byte_limit(canonical=True)
    assert normalize_preferences_blob(blob) == blob


@pytest.mark.parametrize("payload", [None, [], "invalid"])
@pytest.mark.parametrize("route", ["/api/register", "/api/preferences"])
def test_non_object_payload_is_rejected_without_changes(payload, route):
    async def exercise():
        runtime_env = env()
        headers = {}
        original = None
        if route == "/api/preferences":
            await register(runtime_env)
            verified = await verify(runtime_env, delivered_token(runtime_env))
            headers["cookie"] = cookie_from_set_cookie(verified.headers["set-cookie"])
            original = runtime_env.DB.users[0]["preferences_blob"]
        deliveries_before = len(runtime_env.deliveries)
        response = await worker.handle_request(
            FakeRequest(
                "https://example.com" + route,
                method="PATCH" if route == "/api/preferences" else "POST",
                headers=headers,
                payload=payload,
            ),
            runtime_env,
        )
        assert len(runtime_env.deliveries) == deliveries_before
        if route == "/api/preferences":
            assert response.status == 422
            assert runtime_env.DB.users[0]["preferences_blob"] == original
        else:
            assert response.status == 400
            assert runtime_env.DB.users == []

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "blob",
    [
        None,
        {},
        "not-json",
        "null",
        "[]",
        "{}",
        "{" * 5000,
        profile_blob(names=()),
        profile_blob(names=("unknown_type",)),
        profile_blob(names=("live_music", "live_music")),
        profile_blob(names=("live_music",) * 13),
        json.dumps({"top_interest_clusters": [None]}),
        json.dumps({"top_interest_clusters": [{"name": []}]}),
        json.dumps({"top_interest_clusters": "live_music"}),
        " " * 16_385,
        pytest.param(
            profile_at_byte_limit(canonical=False),
            id="canonicalized-profile-over-limit",
        ),
        *[
            pytest.param(
                json.dumps(json.loads(profile_blob()) | {"audience": "NUMBER"}).replace(
                    '"NUMBER"', number
                ),
                id=f"non-finite-number-{number}",
            )
            for number in ("NaN", "Infinity", "-Infinity", "1e400")
        ],
    ],
)
@pytest.mark.parametrize("route", ["/api/register", "/api/preferences"])
def test_invalid_interests_never_write_or_send_email(blob, route):
    async def exercise():
        runtime_env = env()
        headers = {}
        original = None
        if route == "/api/preferences":
            await register(runtime_env)
            verified = await verify(runtime_env, delivered_token(runtime_env))
            headers["cookie"] = cookie_from_set_cookie(verified.headers["set-cookie"])
            original = runtime_env.DB.users[0]["preferences_blob"]
        deliveries_before = len(runtime_env.deliveries)
        response = await worker.handle_request(
            FakeRequest(
                "https://example.com" + route,
                method="PATCH" if route == "/api/preferences" else "POST",
                headers=headers,
                payload={"email": "reader@example.com", "preferences_blob": blob},
            ),
            runtime_env,
        )
        assert response.status == 422
        assert (await response.json())["field"] == "interests"
        assert len(runtime_env.deliveries) == deliveries_before
        if route == "/api/preferences":
            assert runtime_env.DB.users[0]["preferences_blob"] == original
        else:
            assert runtime_env.DB.users == []
            assert runtime_env.DB.magic_links == []

    asyncio.run(exercise())
