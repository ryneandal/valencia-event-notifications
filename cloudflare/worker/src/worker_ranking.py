import json
from dataclasses import dataclass
from typing import Any

from worker_runtime import env_value, to_python

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
RANK_TIMEOUT_MS = 30_000
PROFILE_FIELDS = (
    "audience",
    "location_scope",
    "top_interest_clusters",
    "strong_positive_signals",
    "strong_negative_signals",
    "seasonal_anchors",
)


@dataclass(frozen=True)
class Ranking:
    events: list[dict[str, Any]]
    model_id: str
    used_fallback: bool
    error_code: str | None = None


def load_profile(preferences_blob: str | None) -> dict[str, Any]:
    """Validate and return only the six ranking profile fields."""
    try:
        value = json.loads(preferences_blob or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_profile_json") from exc
    if not isinstance(value, dict):
        raise ValueError("invalid_profile_shape")
    if any(field not in value for field in PROFILE_FIELDS):
        raise ValueError("incomplete_profile")
    return {field: value[field] for field in PROFILE_FIELDS}


def openrouter_payload(
    profile: dict[str, Any],
    events: list[dict[str, Any]],
    model_id: str,
) -> dict[str, Any]:
    """Build a privacy-bounded request containing no subscriber identity."""
    candidates = [
        {
            "event_key": event["event_key"],
            "title": event["title"],
            "start": event["start_at"],
            "url": event["url"],
            "description": event.get("description", ""),
            "source": event["source"],
        }
        for event in events
    ]
    instructions = (
        "Rank up to 8 events for this profile. Return JSON only as "
        '{"recommendations":[{"event_key":"...","reason":"..."}]}. '
        "Use only supplied event_key values. Keep each reason under 180 characters."
    )
    return {
        "model": model_id,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": instructions},
            {
                "role": "user",
                "content": json.dumps(
                    {"profile": profile, "events": candidates},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        ],
    }


def _extract_json(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1]).strip()
        if stripped.startswith("json"):
            stripped = stripped[4:].lstrip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("missing_json_object")
    value = json.loads(stripped[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("invalid_ranking_shape")
    return value


def validate_ranking(
    content: str, events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Validate provider JSON and attach the canonical event records."""
    value = _extract_json(content)
    recommendations = value.get("recommendations")
    if not isinstance(recommendations, list) or not recommendations:
        raise ValueError("invalid_recommendations")

    known = {str(event["event_key"]): event for event in events}
    seen: set[str] = set()
    ranked: list[dict[str, Any]] = []
    for item in recommendations[:8]:
        if not isinstance(item, dict):
            raise ValueError("invalid_recommendation")
        key = item.get("event_key")
        reason = item.get("reason")
        if not isinstance(key, str) or key not in known or key in seen:
            raise ValueError("unknown_or_duplicate_event")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("missing_reason")
        seen.add(key)
        ranked.append({**known[key], "relevance_reason": reason.strip()[:240]})
    return ranked


def deterministic_ranking(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a stable, useful ordering when the provider is unavailable."""
    ordered = sorted(
        events,
        key=lambda event: (
            str(event.get("start_at", "")),
            str(event.get("title", "")).casefold(),
            str(event.get("event_key", "")),
        ),
    )
    return [
        {
            **event,
            "relevance_reason": "A timely event within your selected València scope.",
        }
        for event in ordered[:8]
    ]


async def _call_openrouter(env: Any, body: dict[str, Any]) -> dict[str, Any]:
    fake = env_value(env, "OPENROUTER_FETCH")
    if callable(fake):
        result = await fake(body)
        if not isinstance(result, dict):
            raise RuntimeError("invalid_provider_response")
        return result

    api_key = str(env_value(env, "OPENROUTER_API_KEY", "")).strip()
    if not api_key:
        raise RuntimeError("missing_api_key")
    try:  # Imports are provided by the Cloudflare Python runtime.
        from js import AbortSignal, Object, fetch  # type: ignore[import-not-found]
        from pyodide.ffi import to_js  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - Cloudflare runtime boundary
        raise RuntimeError("fetch_runtime_unavailable") from exc

    options = to_js(
        {
            "method": "POST",
            "headers": {
                "authorization": f"Bearer {api_key}",
                "content-type": "application/json",
                "http-referer": "https://valencia-event-notifications.pages.dev",
                "x-title": "Brisa València Events",
            },
            "body": json.dumps(body, ensure_ascii=False),
            "signal": AbortSignal.timeout(RANK_TIMEOUT_MS),
        },
        dict_converter=Object.fromEntries,
    )
    response = await fetch(OPENROUTER_URL, options)
    if not bool(response.ok):
        raise RuntimeError(f"http_{int(response.status)}")
    value = to_python(await response.json())
    if not isinstance(value, dict):
        raise RuntimeError("invalid_provider_response")
    return value


def _response_content(response: dict[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("missing_provider_content") from exc
    if not isinstance(content, str):
        raise ValueError("invalid_provider_content")
    return content


def _error_code(error: Exception) -> str:
    value = "_".join(str(error).strip().lower().split())
    return value[:64] if value else error.__class__.__name__.lower()[:64]


async def rank_events(
    env: Any,
    preferences_blob: str | None,
    events: list[dict[str, Any]],
) -> Ranking:
    """Rank candidates with OpenRouter, falling back deterministically."""
    if not events:
        return Ranking([], "deterministic", True)
    try:
        profile = load_profile(preferences_blob)
    except ValueError as error:
        return Ranking(
            deterministic_ranking(events),
            "deterministic",
            True,
            _error_code(error),
        )

    model_id = str(env_value(env, "OPENROUTER_MODEL", DEFAULT_MODEL)).strip()
    try:
        response = await _call_openrouter(
            env, openrouter_payload(profile, events, model_id)
        )
        ranked = validate_ranking(_response_content(response), events)
        return Ranking(ranked, model_id, False)
    except Exception as error:
        return Ranking(
            deterministic_ranking(events),
            "deterministic",
            True,
            _error_code(error),
        )
